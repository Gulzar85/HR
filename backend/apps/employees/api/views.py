"""Employee REST API (``/api/v1/employees/``) - thin adapters over the employee services.

Every object lookup goes through the scoped selector (out-of-scope = 404); every write goes through a
service (permission + scope + validation + audit + outbox). ``HasPerm`` denies unmapped methods.
"""

from __future__ import annotations

from typing import Any

from django.http import Http404
from rest_framework import generics, status
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.api.permissions import HasPerm
from apps.api.responses import error_payload, success
from apps.common.exceptions import ValidationException
from apps.common.request_context import RequestContext

from .. import permissions as P
from ..filters import EmployeeFilter
from ..selectors import get_employee, get_employee_detail, get_employee_list, get_employee_timeline
from ..services import (
    AddressService,
    ContactService,
    EmergencyContactService,
    EmployeeService,
    IdentifierService,
    record_event,
)
from . import serializers as s

_ctx = RequestContext.from_request


class _EmployeeMixin:
    def employee(self):
        if not hasattr(self, "_emp"):
            self._emp = get_employee(self.request.user, self.kwargs["pk"])  # type: ignore[attr-defined]
        return self._emp

    def child(self, relation: str):
        obj = getattr(self.employee(), relation).filter(pk=self.kwargs["item"]).first()
        if obj is None:
            raise Http404
        return obj


class EmployeeListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [HasPerm]
    permission_map = {"GET": P.VIEW, "POST": P.ADD}
    serializer_class = s.EmployeeListSerializer
    filterset_class = EmployeeFilter

    def get_queryset(self):
        return get_employee_list(self.request.user)

    def create(self, request, *args, **kwargs):
        ser = s.EmployeeCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        payload: dict[str, Any] = {
            "person_data": dict(d["person"]),
            "identifiers": [dict(x) for x in d.get("identifiers", [])],
            "contacts": [dict(x) for x in d.get("contacts", [])],
        }
        if not d.get("confirm_duplicates"):
            report = EmployeeService.check_duplicates(actor=request.user, **payload)
            if report:
                return _duplicates_response(report)
        employee = EmployeeService.create_employee(
            actor=request.user,
            status=d.get("employee_status") or "active",
            addresses=[dict(x) for x in d.get("addresses", [])],
            emergency_contacts=[dict(x) for x in d.get("emergency_contacts", [])],
            ctx=_ctx(request),
            **payload,
        )
        employee = get_employee_detail(request.user, employee.pk)
        return success(
            s.EmployeeDetailSerializer(employee, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


def _duplicates_response(report):
    from rest_framework.response import Response

    body = error_payload(
        "possible_duplicate",
        "Possible duplicate employees found. Re-submit with confirm_duplicates=true to create anyway.",
        {
            "matches": [
                {"id": str(m.employee.pk), "code": m.code, "signal": m.signal} for m in report
            ]
        },
    )
    return Response(body, status=status.HTTP_409_CONFLICT)


class EmployeeDetailAPI(_EmployeeMixin, APIView):
    permission_classes = [HasPerm]
    permission_map = {"GET": P.VIEW, "PATCH": P.CHANGE_PERSON}

    def get(self, request, pk):
        employee = get_employee_detail(request.user, pk)
        return success(s.EmployeeDetailSerializer(employee, context={"request": request}).data)

    def patch(self, request, pk):
        ser = s.EmployeeUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        EmployeeService.update_employee(
            self.employee(),
            actor=request.user,
            person_data=dict(ser.validated_data),
            ctx=_ctx(request),
        )
        return success(
            s.EmployeeDetailSerializer(
                get_employee_detail(request.user, pk), context={"request": request}
            ).data
        )


class EmployeeStatusAPI(_EmployeeMixin, APIView):
    permission_classes = [HasPerm]
    permission_map = {"POST": P.VIEW}  # the service decides change vs archive permission

    def post(self, request, pk):
        ser = s.StatusChangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        emp = self.employee()
        if emp.is_archived and d["employee_status"] == "active":
            emp = EmployeeService.reactivate(
                emp, actor=request.user, reason=d["reason"], ctx=_ctx(request)
            )
        else:
            emp = EmployeeService.change_status(
                emp,
                actor=request.user,
                status=d["employee_status"],
                reason=d["reason"],
                ctx=_ctx(request),
            )
        return success(s.EmployeeListSerializer(get_employee(request.user, emp.pk)).data)


class EmployeeUserLinkAPI(_EmployeeMixin, APIView):
    permission_classes = [HasPerm]
    permission_map = {"POST": P.LINK_USER, "DELETE": P.LINK_USER}

    def post(self, request, pk):
        ser = s.LinkUserSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=ser.validated_data["email"]).first()
        if user is None:
            raise ValidationException(
                "No user account with that email.", details={"email": ["Not found."]}
            )
        EmployeeService.link_user(self.employee(), actor=request.user, user=user, ctx=_ctx(request))
        return success({"linked": True})

    def delete(self, request, pk):
        EmployeeService.unlink_user(self.employee(), actor=request.user, ctx=_ctx(request))
        return success({"linked": False})


# ------------------------------------------------------------------------ child collections
class _ChildListAPI(_EmployeeMixin, APIView):
    permission_classes = [HasPerm]
    relation: str
    read_serializer: type
    write_serializer: type

    def list_items(self):
        return getattr(self.employee(), self.relation).all()

    def get(self, request, pk):
        return success(
            self.read_serializer(
                self.list_items(), many=True, context=self.serializer_context()
            ).data
        )

    def serializer_context(self):
        return {"request": self.request}

    def post(self, request, pk):
        ser = self.write_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = {k: v for k, v in ser.validated_data.items() if v not in (None, "")}
        obj = self.create(data)
        return success(
            self.read_serializer(obj, context=self.serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class ContactsAPI(_ChildListAPI):
    relation = "contacts"
    read_serializer = s.EmployeeContactSerializer
    write_serializer = s.ContactWriteSerializer
    permission_map = {"GET": P.VIEW, "POST": P.MANAGE_CONTACTS}

    def create(self, data):
        return ContactService.add_contact(
            employee=self.employee(), actor=self.request.user, data=data, ctx=_ctx(self.request)
        )


class AddressesAPI(_ChildListAPI):
    relation = "addresses"
    read_serializer = s.EmployeeAddressSerializer
    write_serializer = s.AddressWriteSerializer
    permission_map = {"GET": P.VIEW_SENSITIVE_CONTACTS, "POST": P.MANAGE_ADDRESSES}

    def create(self, data):
        return AddressService.add_address(
            employee=self.employee(), actor=self.request.user, data=data, ctx=_ctx(self.request)
        )


class EmergencyContactsAPI(_ChildListAPI):
    relation = "emergency_contacts"
    read_serializer = s.EmergencyContactSerializer
    write_serializer = s.EmergencyWriteSerializer
    permission_map = {"GET": P.VIEW_EMERGENCY_CONTACTS, "POST": P.MANAGE_EMERGENCY_CONTACTS}

    def create(self, data):
        return EmergencyContactService.add_emergency_contact(
            employee=self.employee(), actor=self.request.user, data=data, ctx=_ctx(self.request)
        )


class IdentifiersAPI(_ChildListAPI):
    """``GET ?reveal=1`` returns unmasked values to holders of both identifier permissions; the
    read is audited and recorded on the (sensitive) timeline."""

    relation = "identifiers"
    read_serializer = s.EmployeeIdentifierSerializer
    write_serializer = s.IdentifierWriteSerializer
    permission_map = {"GET": P.VIEW_IDENTIFIERS, "POST": P.MANAGE_IDENTIFIERS}

    def serializer_context(self):
        reveal = self.request.query_params.get("reveal") == "1" and self.request.user.has_perm(
            P.VIEW_SENSITIVE_IDENTITY
        )
        return {"request": self.request, "reveal": reveal}

    def get(self, request, pk):
        response = super().get(request, pk)
        if self.serializer_context()["reveal"]:
            employee = self.employee()
            IdentifierService.record_read(
                employee=employee, actor=request.user, count=employee.identifiers.count()
            )
            record_event(
                employee=employee,
                event_type="identifier_viewed",
                summary="Identifiers viewed unmasked (API)",
                actor=request.user,
                is_sensitive=True,
            )
        return response

    def create(self, data):
        return IdentifierService.add_identifier(
            employee=self.employee(), actor=self.request.user, data=data, ctx=_ctx(self.request)
        )


class IdentifierVerifyAPI(_EmployeeMixin, APIView):
    permission_classes = [HasPerm]
    permission_map = {"POST": P.MANAGE_IDENTIFIERS}

    def post(self, request, pk, item):
        ser = s.VerificationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = IdentifierService.set_verification(
            self.child("identifiers"),
            actor=request.user,
            status=ser.validated_data["verification_status"],
            ctx=_ctx(request),
        )
        return success(s.EmployeeIdentifierSerializer(obj, context={"request": request}).data)


class ChildDeleteAPI(_EmployeeMixin, APIView):
    """DELETE a contact / emergency contact / identifier, or close an address (never deleted)."""

    permission_classes = [HasPerm]
    relation: str
    permission_map: dict = {}

    def delete(self, request, pk, item):
        obj = self.child(self.relation)
        ctx = _ctx(request)
        if self.relation == "contacts":
            ContactService.remove_contact(obj, actor=request.user, ctx=ctx)
        elif self.relation == "emergency_contacts":
            EmergencyContactService.remove_emergency_contact(obj, actor=request.user, ctx=ctx)
        elif self.relation == "identifiers":
            IdentifierService.remove_identifier(obj, actor=request.user, ctx=ctx)
        elif self.relation == "addresses":
            AddressService.close_address(obj, actor=request.user, ctx=ctx)
        return success({"removed": True})


class TimelineAPI(_EmployeeMixin, APIView):
    permission_classes = [HasPerm]
    permission_map = {"GET": P.VIEW_TIMELINE}

    def get(self, request, pk):
        entries = get_employee_timeline(request.user, self.employee(), limit=200)
        return success(s.EmployeeTimelineSerializer(entries, many=True).data)


def delete_view(relation: str, perm: str):
    return type(
        f"{relation.title().replace('_', '')}DeleteAPI",
        (ChildDeleteAPI,),
        {"relation": relation, "permission_map": {"DELETE": perm}},
    )

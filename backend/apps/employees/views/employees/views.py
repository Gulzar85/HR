"""Employee list, detail, create, status, account link, export and timeline (CBVs only)."""

from __future__ import annotations

import csv
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView
from django_filters.views import FilterView

from apps.accounts.models import User
from apps.common.request_context import RequestContext
from apps.common.views.base import AdminAccessMixin, PostActionView, ServiceFormView
from apps.common.views.mixins import HtmxTemplateMixin

from ... import permissions as P
from ...filters import EmployeeFilter
from ...forms import (
    AddressForm,
    DuplicateConfirmForm,
    EmergencyContactForm,
    IdentifierForm,
    InitialContactsForm,
    LinkUserForm,
    PersonForm,
    PhotoForm,
    StatusForm,
)
from ...models import SELECTABLE_STATUSES, EmployeeStatus
from ...selectors import get_employee_detail, get_employee_list
from ...services import EmployeeService, IdentifierService
from ..base import (
    FORM_ERRORS,
    EmployeeObjectMixin,
    apply_errors,
    capabilities,
    detail_context,
    section_context,
)


class EmployeeListView(AdminAccessMixin, HtmxTemplateMixin, FilterView):
    permission_required = P.VIEW
    filterset_class = EmployeeFilter
    template_name = "employees/list.html"
    htmx_template_name = "employees/_table.html"
    context_object_name = "employees"
    nav_section = "employees"
    strict = False

    def get_paginate_by(self, queryset) -> int:
        return settings.EMS_ADMIN_PAGE_SIZE

    def get_queryset(self):
        return get_employee_list(self.request.user)

    def get_breadcrumbs(self):
        return [("People", None), ("Employees", None)]

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        data["querystring"] = params.urlencode()
        data["caps"] = capabilities(self.request.user)
        data["can_add"] = self.request.user.has_perm(P.ADD)
        return data


class EmployeeDetailView(EmployeeObjectMixin, AdminAccessMixin, DetailView):
    permission_required = P.VIEW
    template_name = "employees/detail.html"
    context_object_name = "employee"
    nav_section = "employees"

    def get_object(self, queryset=None):
        return get_employee_detail(self.request.user, self.kwargs["pk"])

    def get_breadcrumbs(self):
        return self.employee_crumbs()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(detail_context(self.request, self.object))
        data["status_choices"] = _status_choices(self.request.user, self.object)
        return data


def _status_choices(user: Any, employee: Any) -> list[str]:
    caps = capabilities(user)
    if employee.is_archived:
        return [EmployeeStatus.ACTIVE] if caps["archive"] else []
    choices = (
        [s for s in SELECTABLE_STATUSES if s != employee.employee_status] if caps["change"] else []
    )
    if caps["archive"]:
        choices.append(EmployeeStatus.ARCHIVED)
    return [c for c in choices if c != employee.employee_status]


class EmployeeCreateView(AdminAccessMixin, TemplateView):
    """One page: person, primary contacts, address, emergency contact, identifier (optional parts
    may be left empty). Possible duplicates are shown and must be acknowledged - never auto-merged."""

    permission_required = P.ADD
    template_name = "employees/create.html"
    nav_section = "employee_create"

    def get_breadcrumbs(self):
        return [("People", None), ("Employees", reverse("employees:list")), ("New", None)]

    def forms(self, data=None, files=None) -> dict[str, Any]:
        caps = capabilities(self.request.user)
        forms = {
            "person": PersonForm(data, prefix="person"),
            "photo": PhotoForm(data, files, prefix="photo"),
            "contacts": InitialContactsForm(data, prefix="contacts"),
            "address": AddressForm(data, prefix="address", optional=True),
            "emergency": EmergencyContactForm(data, prefix="emergency", optional=True),
            "confirm": DuplicateConfirmForm(data, prefix="dup"),
        }
        forms["photo"].fields.pop("remove_photo")
        if caps["manage_identifiers"]:
            forms["identifier"] = IdentifierForm(data, prefix="identifier", optional=True)
        return forms

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.setdefault("forms", self.forms())
        return data

    def post(self, request, *args, **kwargs):
        forms = self.forms(request.POST, request.FILES)
        if not all(f.is_valid() for f in forms.values()):
            return self.render_to_response(self.get_context_data(forms=forms))
        person_data = forms["person"].cleaned_data
        contacts = forms["contacts"].contacts()
        identifiers = []
        if "identifier" in forms and not forms["identifier"].is_blank():
            identifiers = [
                {k: v for k, v in forms["identifier"].cleaned_data.items() if v not in (None, "")}
            ]
        addresses = (
            []
            if forms["address"].is_blank()
            else [{k: v for k, v in forms["address"].cleaned_data.items() if v not in (None, "")}]
        )
        emergency = (
            []
            if forms["emergency"].is_blank()
            else [{k: v for k, v in forms["emergency"].cleaned_data.items() if v not in (None, "")}]
        )
        if not forms["confirm"].cleaned_data.get("confirm_duplicates"):
            report = EmployeeService.check_duplicates(
                actor=request.user,
                person_data=person_data,
                identifiers=identifiers,
                contacts=contacts,
            )
            if report:
                return self.render_to_response(
                    self.get_context_data(forms=forms, duplicates=report)
                )
        try:
            employee = EmployeeService.create_employee(
                actor=request.user,
                person_data=person_data,
                contacts=contacts,
                identifiers=identifiers,
                addresses=addresses,
                emergency_contacts=emergency,
                profile_photo=forms["photo"].cleaned_data.get("profile_photo"),
                ctx=RequestContext.from_request(request),
            )
        except FORM_ERRORS as exc:
            target = _route_error(forms, exc)
            apply_errors(forms[target], exc)
            return self.render_to_response(self.get_context_data(forms=forms))
        messages.success(request, f"{employee.code} created.")
        return redirect("employees:detail", pk=employee.pk)


def _route_error(forms: dict[str, Any], exc: Any) -> str:
    """Send a service error to the form that owns the offending field."""
    fields = set((exc.details or {}).keys())
    for name in ("identifier", "address", "emergency", "photo", "person"):
        if name in forms and fields & set(forms[name].fields):
            return name
    if getattr(exc, "code", "") in ("duplicate_identifier",) and "identifier" in forms:
        return "identifier"
    return "person"


class EmployeeEditView(EmployeeObjectMixin, ServiceFormView):
    """Edit personal identity + photo. DOB/gender/nationality/photo appear only for users allowed to
    see them; the service re-checks (``view_sensitive_identity``) regardless."""

    permission_required = P.CHANGE_PERSON
    template_name = "employees/edit.html"
    form_class = PersonForm
    nav_section = "employees"
    page_title = "Edit personal details"
    success_message = "Personal details saved."

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["sensitive"] = capabilities(self.request.user)["view_sensitive"]
        return kw

    def get_initial(self):
        p = self.employee.person
        return {
            f: getattr(p, f)
            for f in (
                "first_name",
                "middle_name",
                "last_name",
                "preferred_name",
                "date_of_birth",
                "gender",
                "nationality",
            )
        }

    def get_breadcrumbs(self):
        return self.employee_crumbs("Edit")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(
            employee=self.employee, cancel_url=reverse("employees:detail", args=[self.employee.pk])
        )
        if capabilities(self.request.user)["view_sensitive"]:
            data["photo_form"] = kwargs.get("photo_form") or PhotoForm(prefix="photo")
        return data

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        photo_form = (
            PhotoForm(request.POST, request.FILES, prefix="photo")
            if capabilities(request.user)["view_sensitive"]
            else None
        )
        if not form.is_valid() or (photo_form is not None and not photo_form.is_valid()):
            return self.render_to_response(self.get_context_data(form=form, photo_form=photo_form))
        photo = photo_form.cleaned_data if photo_form else {}
        try:
            EmployeeService.update_employee(
                self.employee,
                actor=request.user,
                person_data=form.cleaned_data,
                profile_photo=photo.get("profile_photo"),
                remove_photo=bool(photo.get("remove_photo")),
                ctx=self.ctx,
            )
        except FORM_ERRORS as exc:
            if photo_form is not None and "profile_photo" in (exc.details or {}):
                apply_errors(photo_form, exc)
            else:
                apply_errors(form, exc)
            return self.render_to_response(self.get_context_data(form=form, photo_form=photo_form))
        messages.success(request, self.success_message)
        return redirect("employees:detail", pk=self.employee.pk)


class EmployeeStatusView(EmployeeObjectMixin, ServiceFormView):
    permission_required = P.VIEW
    form_class = StatusForm
    template_name = "employees/status.html"
    nav_section = "employees"
    page_title = "Change status"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["choices"] = _status_choices(self.request.user, self.employee)
        return kw

    def get_initial(self):
        return {"employee_status": self.request.GET.get("status")}

    def get_breadcrumbs(self):
        return self.employee_crumbs("Status")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(
            employee=self.employee, cancel_url=reverse("employees:detail", args=[self.employee.pk])
        )
        return data

    def perform(self, form):
        d = form.cleaned_data
        if self.employee.is_archived and d["employee_status"] == EmployeeStatus.ACTIVE:
            emp = EmployeeService.reactivate(
                self.employee, actor=self.request.user, reason=d["reason"], ctx=self.ctx
            )
        else:
            emp = EmployeeService.change_status(
                self.employee,
                actor=self.request.user,
                status=d["employee_status"],
                reason=d["reason"],
                ctx=self.ctx,
            )
        self.success_message = f"{emp.code} is now {emp.get_employee_status_display().lower()}."

    def get_success_url(self):
        return reverse("employees:detail", args=[self.employee.pk])


class EmployeeLinkUserView(EmployeeObjectMixin, ServiceFormView):
    permission_required = P.LINK_USER
    form_class = LinkUserForm
    template_name = "employees/status.html"
    nav_section = "employees"
    page_title = "Link user account"
    success_message = "User account linked."

    def get_breadcrumbs(self):
        return self.employee_crumbs("User account")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(
            employee=self.employee,
            cancel_url=reverse("employees:detail", args=[self.employee.pk]),
            submit_label="Link account",
        )
        return data

    def perform(self, form):
        user = User.objects.filter(email__iexact=form.cleaned_data["email"].strip()).first()
        if user is None:
            from apps.common.exceptions import ValidationException

            raise ValidationException(
                "No user account with that email.",
                details={"email": ["No user account with that email."]},
            )
        EmployeeService.link_user(self.employee, actor=self.request.user, user=user, ctx=self.ctx)

    def get_success_url(self):
        return reverse("employees:detail", args=[self.employee.pk])


class EmployeeUnlinkUserView(EmployeeObjectMixin, PostActionView):
    permission_required = P.LINK_USER
    success_message = "User account unlinked. The account itself was not changed."

    def perform(self, request, *args, **kwargs):
        EmployeeService.unlink_user(self.employee, actor=request.user, ctx=self.ctx)

    def get_success_url(self, *args, **kwargs):
        return reverse("employees:detail", args=[self.employee.pk])


class EmployeePhotoView(EmployeeObjectMixin, AdminAccessMixin, View):
    """Serves the profile photo through authorization (never via a public MEDIA URL)."""

    permission_required = (P.VIEW, P.VIEW_SENSITIVE_IDENTITY)

    def get(self, request, *args, **kwargs):
        photo = self.employee.person.profile_photo
        if not photo:
            return HttpResponse(status=404)
        from PIL import Image

        try:
            with photo.open("rb") as fh:
                fmt = (Image.open(fh).format or "").lower()
                fh.seek(0)
                body = fh.read()
        except Exception:  # noqa: BLE001
            return HttpResponse(status=404)
        content_type = {
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
        }.get(fmt)
        if content_type is None:
            return HttpResponse(status=404)
        response = HttpResponse(body, content_type=content_type)
        response["Cache-Control"] = "private, max-age=300"
        response["Content-Disposition"] = "inline"
        return response


class IdentifierRevealView(EmployeeObjectMixin, AdminAccessMixin, View):
    """POST-only: re-render the identifiers section unmasked for authorized users; audited."""

    permission_required = (P.VIEW_IDENTIFIERS, P.VIEW_SENSITIVE_IDENTITY)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        employee = self.employee
        ctx = section_context(request, employee, "identifiers", revealed=True)
        IdentifierService.record_read(
            employee=employee, actor=request.user, count=len(ctx.get("identifiers", []))
        )
        from ...services import record_event

        record_event(
            employee=employee, event_type="identifier_viewed", summary="Identifiers viewed unmasked",
            actor=request.user, is_sensitive=True,
        )  # fmt: skip
        return render(request, "employees/sections/_identifiers.html", ctx)


class EmployeeTimelineView(EmployeeObjectMixin, AdminAccessMixin, View):
    """HTMX partial: refresh the timeline section."""

    permission_required = (P.VIEW, P.VIEW_TIMELINE)

    def get(self, request, *args, **kwargs):
        return render(
            request,
            "employees/sections/_timeline.html",
            section_context(request, self.employee, "timeline"),
        )


EXPORT_COLUMNS = [
    ("Employee code", lambda e: e.code),
    ("First name", lambda e: e.person.first_name),
    ("Last name", lambda e: e.person.last_name),
    ("Preferred name", lambda e: e.person.preferred_name),
    ("Status", lambda e: e.get_employee_status_display()),
    (
        "Email",
        lambda e: next((c.value for c in e.primary_contacts if c.contact_type == "email"), ""),
    ),
    (
        "Mobile",
        lambda e: next((c.value for c in e.primary_contacts if c.contact_type == "mobile"), ""),
    ),
    ("Has user account", lambda e: "yes" if e.user_id else "no"),
    ("Created", lambda e: e.created_at.date().isoformat()),
]


class _Echo:
    def write(self, value):
        return value


class EmployeeExportView(AdminAccessMixin, View):
    """CSV export of the *filtered, scoped* list. Non-sensitive columns only; audited; capped."""

    permission_required = (P.VIEW, P.EXPORT)

    def get(self, request, *args, **kwargs):
        qs = EmployeeFilter(
            request.GET, queryset=get_employee_list(request.user), request=request
        ).qs
        limit = settings.EMS_EMPLOYEE_EXPORT_MAX_ROWS
        rows = list(qs[: limit + 1])
        if len(rows) > limit:
            messages.error(
                request, f"Too many rows ({limit}+). Narrow the filters before exporting."
            )
            return redirect(reverse("employees:list") + "?" + request.GET.urlencode())
        from apps.audit.services import record_audit

        ctx = RequestContext.from_request(request)
        record_audit(
            action="employees.employee_exported", actor=request.user, obj_type="employee", obj_id="",
            changes={"rows": len(rows), "filters": dict(request.GET.items()), "columns": [c for c, _ in EXPORT_COLUMNS]},
            ip_address=ctx.ip_address, user_agent=ctx.user_agent,
        )  # fmt: skip
        writer = csv.writer(_Echo())

        def stream():
            yield writer.writerow([c for c, _ in EXPORT_COLUMNS])
            for e in rows:
                yield writer.writerow([_safe(fn(e)) for _, fn in EXPORT_COLUMNS])

        response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="employees.csv"'
        return response


def _safe(value: Any) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text

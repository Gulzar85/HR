"""Organization REST API. Same services as the web UI; every lookup is scope-filtered.

Out-of-scope or unknown ids return 404 (no existence oracle). Methods not in ``permission_map``
are denied by ``HasPerm``.
"""

from __future__ import annotations

from typing import Any

from rest_framework import generics, status
from rest_framework.views import APIView

from apps.api.permissions import HasPerm
from apps.api.responses import success
from apps.common.request_context import RequestContext

from ..filters import FILTERS
from ..hierarchy import ORG_TYPES
from ..selectors import get_organization_tree, get_unit_for_user, history_for, visible_units
from ..services import OrganizationService
from . import serializers as s

_ctx = RequestContext.from_request


class _OrgAPIMixin:
    type_key: str

    @property
    def org_type(self):
        return ORG_TYPES[self.type_key]

    def get_unit(self):
        return get_unit_for_user(self.request.user, self.type_key, self.kwargs["pk"])  # type: ignore[attr-defined]


class OrgListCreateAPI(_OrgAPIMixin, generics.ListCreateAPIView):
    permission_classes = [HasPerm]

    @property
    def permission_map(self) -> dict[str, str]:
        return {"GET": self.org_type.perm("view"), "POST": self.org_type.perm("add")}

    def get_queryset(self):
        return visible_units(self.request.user, self.type_key)

    def get_serializer_class(self):
        return s.read_serializer(self.type_key)

    @property
    def filterset_class(self):
        return FILTERS[self.type_key]

    def create(self, request, *args, **kwargs):
        ser = s.write_serializer(self.type_key, create=True)(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        parent_id = data.pop("parent_id", None)
        initial_status = data.pop("status", None)
        parent = (
            get_unit_for_user(request.user, self.org_type.parent_key, parent_id)
            if self.org_type.parent_key
            else None
        )
        obj = OrganizationService.create(
            self.type_key,
            actor=request.user,
            data=data,
            parent=parent,
            status=initial_status,
            ctx=_ctx(request),
        )
        return success(s.read_serializer(self.type_key)(obj).data, status=status.HTTP_201_CREATED)


class OrgDetailAPI(_OrgAPIMixin, APIView):
    permission_classes = [HasPerm]

    @property
    def permission_map(self) -> dict[str, str]:
        return {"GET": self.org_type.perm("view"), "PATCH": self.org_type.perm("change")}

    def get(self, request, pk):
        return success(s.read_serializer(self.type_key)(self.get_unit()).data)

    def patch(self, request, pk):
        unit = self.get_unit()
        ser = s.write_serializer(self.type_key, create=False)(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        obj = OrganizationService.update(
            unit, actor=request.user, data=dict(ser.validated_data), ctx=_ctx(request)
        )
        return success(s.read_serializer(self.type_key)(obj).data)


class OrgStatusAPI(_OrgAPIMixin, APIView):
    permission_classes = [HasPerm]
    permission_map = {"POST": "organizations.change_organization_status"}

    def post(self, request, pk):
        ser = s.StatusSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        obj = OrganizationService.change_status(
            self.get_unit(), d["action"], actor=request.user, reason=d["reason"],
            effective_date=d.get("effective_date"), ctx=_ctx(request),
        )  # fmt: skip
        return success(s.read_serializer(self.type_key)(obj).data)


class OrgMoveAPI(_OrgAPIMixin, APIView):
    permission_classes = [HasPerm]
    permission_map = {"POST": "organizations.move_organization"}

    def post(self, request, pk):
        ser = s.MoveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        unit = self.get_unit()
        new_parent = get_unit_for_user(request.user, self.org_type.parent_key, d["parent_id"])
        obj = OrganizationService.move(
            unit, new_parent, actor=request.user, reason=d["reason"],
            effective_date=d.get("effective_date"), ctx=_ctx(request),
        )  # fmt: skip
        return success(s.read_serializer(self.type_key)(obj).data)


class OrgHistoryAPI(_OrgAPIMixin, APIView):
    permission_classes = [HasPerm]
    permission_map = {"GET": "organizations.view_organization_history"}

    def get(self, request, pk):
        return success(s.HistorySerializer(history_for(self.get_unit(), limit=200), many=True).data)


class OrganizationTreeAPI(APIView):
    permission_classes = [HasPerm]
    permission_map = {"GET": "organizations.view_organization_structure"}

    def get(self, request):
        include_inactive = request.query_params.get("include_inactive", "1") != "0"
        tree = get_organization_tree(request.user, include_inactive=include_inactive)
        _strip_urls(tree)
        return success(tree)


def _strip_urls(nodes: list[dict[str, Any]]) -> None:
    for node in nodes:
        node.pop("url", None)
        node.pop("icon", None)
        _strip_urls(node["children"])


def build(view: type, key: str) -> type:
    """Concrete per-type view class (keeps DRF schema/names readable)."""
    return type(f"{ORG_TYPES[key].model.__name__}{view.__name__}", (view,), {"type_key": key})

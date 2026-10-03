"""Department screens. Behaviour is generic (views/base.py); this module only declares what differs."""

from __future__ import annotations

from ..base import (
    Column,
    OrgCreateView,
    OrgDetailView,
    OrgListView,
    OrgMoveView,
    OrgStatusView,
    OrgUpdateView,
)

KEY = "department"


class _Department:
    type_key = KEY
    columns = [
        Column("Department", "unit"),
        Column("Corporate location", "parent", "location"),
        Column("Short code", "text", "short_code", hide_sm=True),
        Column("Status", "status"),
    ]
    detail_fields = [
        ("Short code", "short_code"),
    ]


class DepartmentListView(_Department, OrgListView):
    pass


class DepartmentDetailView(_Department, OrgDetailView):
    pass


class DepartmentCreateView(_Department, OrgCreateView):
    pass


class DepartmentUpdateView(_Department, OrgUpdateView):
    pass


class DepartmentStatusView(_Department, OrgStatusView):
    pass


class DepartmentMoveView(_Department, OrgMoveView):
    pass

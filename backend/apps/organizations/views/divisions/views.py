"""Division screens. Behaviour is generic (views/base.py); this module only declares what differs."""

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

KEY = "division"


class _Division:
    type_key = KEY
    columns = [
        Column("Division", "unit"),
        Column("Company", "parent", "company"),
        Column("Structure", "text", "get_structure_type_display"),
        Column("Status", "status"),
    ]
    detail_fields = [
        ("Structure", "get_structure_type_display"),
    ]


class DivisionListView(_Division, OrgListView):
    pass


class DivisionDetailView(_Division, OrgDetailView):
    pass


class DivisionCreateView(_Division, OrgCreateView):
    pass


class DivisionUpdateView(_Division, OrgUpdateView):
    pass


class DivisionStatusView(_Division, OrgStatusView):
    pass


class DivisionMoveView(_Division, OrgMoveView):
    pass

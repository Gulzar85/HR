"""Area screens. Behaviour is generic (views/base.py); this module only declares what differs."""

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

KEY = "area"


class _Area:
    type_key = KEY
    columns = [
        Column("Area", "unit"),
        Column("Region", "parent", "region"),
        Column("Status", "status"),
        Column("Effective from", "date", "effective_from", hide_sm=True),
    ]
    detail_fields = []


class AreaListView(_Area, OrgListView):
    pass


class AreaDetailView(_Area, OrgDetailView):
    pass


class AreaCreateView(_Area, OrgCreateView):
    pass


class AreaUpdateView(_Area, OrgUpdateView):
    pass


class AreaStatusView(_Area, OrgStatusView):
    pass


class AreaMoveView(_Area, OrgMoveView):
    pass

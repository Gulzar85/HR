"""Region screens. Behaviour is generic (views/base.py); this module only declares what differs."""

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

KEY = "region"


class _Region:
    type_key = KEY
    columns = [
        Column("Region", "unit"),
        Column("Division", "parent", "division"),
        Column("Status", "status"),
        Column("Effective from", "date", "effective_from", hide_sm=True),
    ]
    detail_fields = []


class RegionListView(_Region, OrgListView):
    pass


class RegionDetailView(_Region, OrgDetailView):
    pass


class RegionCreateView(_Region, OrgCreateView):
    pass


class RegionUpdateView(_Region, OrgUpdateView):
    pass


class RegionStatusView(_Region, OrgStatusView):
    pass


class RegionMoveView(_Region, OrgMoveView):
    pass

"""CorporateLocation screens. Behaviour is generic (views/base.py); this module only declares what differs."""

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

KEY = "corporate_location"


class _CorporateLocation:
    type_key = KEY
    columns = [
        Column("Location", "unit"),
        Column("Division", "parent", "division"),
        Column("City", "text", "city", hide_sm=True),
        Column("Status", "status"),
    ]
    detail_fields = [
        ("City", "city"),
        ("City code", "city_code"),
        ("Address", "address"),
        ("Phone", "phone"),
        ("Email", "email"),
    ]


class CorporateLocationListView(_CorporateLocation, OrgListView):
    pass


class CorporateLocationDetailView(_CorporateLocation, OrgDetailView):
    pass


class CorporateLocationCreateView(_CorporateLocation, OrgCreateView):
    pass


class CorporateLocationUpdateView(_CorporateLocation, OrgUpdateView):
    pass


class CorporateLocationStatusView(_CorporateLocation, OrgStatusView):
    pass


class CorporateLocationMoveView(_CorporateLocation, OrgMoveView):
    pass

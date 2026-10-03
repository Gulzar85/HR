"""Restaurant screens. Behaviour is generic (views/base.py); this module only declares what differs."""

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

KEY = "restaurant"


class _Restaurant:
    type_key = KEY
    columns = [
        Column("Restaurant", "unit"),
        Column("Area", "parent", "area"),
        Column("Region", "parent", "area.region", hide_sm=True),
        Column("City", "text", "city", hide_sm=True),
        Column("Status", "status"),
        Column("Opened", "date", "opening_date", hide_sm=True),
    ]
    detail_fields = [
        ("Short name", "short_name"),
        ("City", "city"),
        ("City code", "city_code"),
        ("Address", "address"),
        ("Latitude", "latitude"),
        ("Longitude", "longitude"),
        ("Phone", "phone"),
        ("Email", "email"),
        ("Opening date", "opening_date"),
        ("Closing date", "closing_date"),
    ]


class RestaurantListView(_Restaurant, OrgListView):
    pass


class RestaurantDetailView(_Restaurant, OrgDetailView):
    pass


class RestaurantCreateView(_Restaurant, OrgCreateView):
    pass


class RestaurantUpdateView(_Restaurant, OrgUpdateView):
    pass


class RestaurantStatusView(_Restaurant, OrgStatusView):
    pass


class RestaurantMoveView(_Restaurant, OrgMoveView):
    pass

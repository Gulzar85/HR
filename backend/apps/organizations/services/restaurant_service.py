from __future__ import annotations

from datetime import date
from typing import Any

from apps.common.services import generate_code

from ..models import OrganizationHistory, RestaurantStatus
from .organization_service import OrganizationService, OrgUnitService

E = OrganizationHistory.Event
R = RestaurantStatus


@OrganizationService.register
class RestaurantService(OrgUnitService):
    """Restaurant lifecycle: planned -> active <-> temporarily closed -> closed (-> reopened/archived)."""

    type_key = "restaurant"
    editable_fields = (
        "name", "short_name", "description", "city", "address",
        "latitude", "longitude", "phone", "email", "opening_date",
    )  # fmt: skip
    create_only_fields = ("city_code",)
    default_status = R.PLANNED
    initial_statuses = frozenset({R.PLANNED, R.ACTIVE})
    transitions = {
        "activate": (frozenset({R.PLANNED}), R.ACTIVE, E.ACTIVATED),
        "temporarily_close": (frozenset({R.ACTIVE}), R.TEMPORARILY_CLOSED, E.TEMPORARILY_CLOSED),
        "reopen": (frozenset({R.TEMPORARILY_CLOSED, R.CLOSED}), R.ACTIVE, E.REOPENED),
        "close": (frozenset({R.ACTIVE, R.TEMPORARILY_CLOSED}), R.CLOSED, E.CLOSED),
        "archive": (frozenset({R.CLOSED, R.PLANNED}), R.ARCHIVED, E.ARCHIVED),
    }

    @classmethod
    def generate_code(cls, fields, parent) -> str:
        return generate_code("RST", scope=fields["city_code"], width=3)  # RST-LHR-001

    @classmethod
    def on_status_change(cls, obj: Any, action: str, when: date) -> None:
        if action == "activate" and not obj.opening_date:
            obj.opening_date = when
        elif action == "close":
            obj.closing_date = when
        elif action == "reopen":
            obj.closing_date = None

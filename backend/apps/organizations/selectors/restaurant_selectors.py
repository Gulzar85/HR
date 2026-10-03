"""Restaurant read queries (used by reports, recruitment and the future Assignment domain)."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from ..models import Area, Region, Restaurant
from .organization_selectors import visible_units


def get_restaurants(user: Any = None) -> QuerySet[Restaurant]:
    return (
        visible_units(user, "restaurant")
        if user is not None
        else (Restaurant.objects.select_related("area__region__division__company").order_by("code"))
    )


def get_restaurants_by_area(area: Area, user: Any = None) -> QuerySet[Restaurant]:
    return get_restaurants(user).filter(area=area)


def get_restaurants_by_region(region: Region, user: Any = None) -> QuerySet[Restaurant]:
    return get_restaurants(user).filter(area__region=region)

"""Area read queries."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from ..models import Area, Region
from .organization_selectors import visible_units


def get_areas(user: Any = None) -> QuerySet[Area]:
    return (
        visible_units(user, "area")
        if user is not None
        else (Area.objects.select_related("region__division__company").order_by("code"))
    )


def get_areas_by_region(region: Region, user: Any = None) -> QuerySet[Area]:
    return get_areas(user).filter(region=region)

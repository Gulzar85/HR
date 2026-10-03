"""Corporate location and department read queries."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from ..models import CorporateLocation, Department
from .organization_selectors import visible_units


def get_corporate_locations(user: Any = None) -> QuerySet[CorporateLocation]:
    return (
        visible_units(user, "corporate_location")
        if user is not None
        else (CorporateLocation.objects.select_related("division__company").order_by("code"))
    )


def get_departments(user: Any = None) -> QuerySet[Department]:
    return (
        visible_units(user, "department")
        if user is not None
        else (Department.objects.select_related("location__division__company").order_by("code"))
    )


def get_departments_by_location(
    location: CorporateLocation, user: Any = None
) -> QuerySet[Department]:
    return get_departments(user).filter(location=location)

"""Company and division read queries."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from ..models import Company, Division, OrgStatus
from .organization_selectors import visible_units


def get_active_companies(user: Any = None) -> QuerySet[Company]:
    qs = visible_units(user, "company") if user is not None else Company.objects.all()
    return qs.filter(status=OrgStatus.ACTIVE)


def get_active_divisions(user: Any = None, company: Company | None = None) -> QuerySet[Division]:
    qs = (
        visible_units(user, "division")
        if user is not None
        else Division.objects.select_related("company")
    )
    if company is not None:
        qs = qs.filter(company=company)
    return qs.filter(status=OrgStatus.ACTIVE)

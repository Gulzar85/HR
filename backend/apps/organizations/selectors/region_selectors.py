"""Region read queries."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Q, QuerySet

from ..models import LIVE_STATUSES, Region
from .organization_selectors import visible_units


def get_regions(user: Any = None) -> QuerySet[Region]:
    qs = (
        visible_units(user, "region")
        if user is not None
        else Region.objects.select_related("division__company")
    )
    return qs.annotate(
        area_count=Count("areas", distinct=True),
        restaurant_count=Count(
            "areas__restaurants",
            filter=Q(areas__restaurants__status__in=LIVE_STATUSES),
            distinct=True,
        ),
    )

"""Date and effective-date helpers.

Effective-dated records use ``effective_from`` (inclusive) and ``effective_to`` (inclusive,
NULL = open-ended).
"""

from __future__ import annotations

from datetime import date

from django.db.models import Q
from django.utils import timezone


def today_local() -> date:
    """Today's date in the configured TIME_ZONE (Asia/Karachi)."""
    return timezone.localdate()


def is_effective(effective_from: date, effective_to: date | None, on: date | None = None) -> bool:
    on = on or today_local()
    return effective_from <= on and (effective_to is None or on <= effective_to)


def date_ranges_overlap(
    start_a: date, end_a: date | None, start_b: date, end_b: date | None
) -> bool:
    """True if two inclusive ranges (open-ended when end is None) overlap."""
    a_before_b_ends = end_b is None or start_a <= end_b
    b_before_a_ends = end_a is None or start_b <= end_a
    return a_before_b_ends and b_before_a_ends


def effective_on_q(on: date | None = None, prefix: str = "") -> Q:
    """Q object selecting rows effective on a date; ``prefix`` for related lookups."""
    on = on or today_local()
    return Q(**{f"{prefix}effective_from__lte": on}) & (
        Q(**{f"{prefix}effective_to__isnull": True}) | Q(**{f"{prefix}effective_to__gte": on})
    )

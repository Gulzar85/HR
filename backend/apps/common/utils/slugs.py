from __future__ import annotations

from django.db.models import QuerySet
from django.utils.text import slugify


def unique_slug(queryset: QuerySet, value: str, field: str = "slug", max_length: int = 50) -> str:
    """Slugify ``value`` and append -2, -3 ... until unique within ``queryset``."""
    base = slugify(value)[:max_length] or "item"
    candidate, n = base, 1
    while queryset.filter(**{field: candidate}).exists():
        n += 1
        suffix = f"-{n}"
        candidate = f"{base[: max_length - len(suffix)]}{suffix}"
    return candidate

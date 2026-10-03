"""Contact lookups used by duplicate detection, data quality and future integrations."""

from __future__ import annotations

from django.db.models import Count, QuerySet

from ..models import Contact, ContactType
from ..validators import normalize_email, normalize_phone

EMAIL_TYPES = (ContactType.EMAIL, ContactType.ALTERNATIVE_EMAIL)


def find_contacts(contact_type: str, value: str) -> QuerySet[Contact]:
    norm = normalize_email(value) if contact_type in EMAIL_TYPES else normalize_phone(value)
    return Contact.objects.filter(contact_type=contact_type, normalized_value=norm).select_related(
        "employee"
    )


def shared_contact_values(contact_types: list[str]) -> QuerySet:
    """(contact_type, normalized_value) pairs used by more than one employee."""
    return (
        Contact.objects.filter(contact_type__in=contact_types)
        .values("contact_type", "normalized_value")
        .annotate(n=Count("employee", distinct=True))
        .filter(n__gt=1)
    )

"""Controlled reference data for the employee domain.

Phase 3 deliberately keeps reference data small and *configuration-driven* rather than promoting
every vocabulary to a database table (docs/architecture/application-boundaries.md: "do not create
hundreds of unnecessary database models"). Two different strategies are used, on purpose:

``Gender`` / ``IdentifierType`` / ``RelationshipType`` / ``ContactType`` / ``AddressType`` /
``VerificationStatus`` / ``NoteVisibility``
    Small, closed vocabularies defined as ``TextChoices``. Adding a value is a one-line change and
    a migration; the value is enforced by a database ``CHECK`` constraint, not only by Python.

``Nationality`` / ``issuing_country``
    Open-ended and country-specific, so the list of accepted countries is **settings-driven**
    (``settings.EMS_COUNTRIES``). Deployment can extend or restrict the list without a migration.
    Values are ISO 3166-1 alpha-2 codes; a validator rejects anything outside the configured set,
    so the database never receives an arbitrary free-text nationality.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

# Countries McDonald's Pakistan operates in / hires from, plus the usual neighbouring and
# common-expat regions. Override entirely with the EMS_COUNTRIES setting.
DEFAULT_COUNTRIES: tuple[tuple[str, str], ...] = (
    ("PK", "Pakistan"),
    ("AF", "Afghanistan"),
    ("AE", "United Arab Emirates"),
    ("AU", "Australia"),
    ("BD", "Bangladesh"),
    ("BH", "Bahrain"),
    ("CA", "Canada"),
    ("CN", "China"),
    ("EG", "Egypt"),
    ("GB", "United Kingdom"),
    ("IN", "India"),
    ("IQ", "Iraq"),
    ("IR", "Iran"),
    ("KW", "Kuwait"),
    ("MY", "Malaysia"),
    ("NG", "Nigeria"),
    ("NP", "Nepal"),
    ("OM", "Oman"),
    ("PH", "Philippines"),
    ("QA", "Qatar"),
    ("SA", "Saudi Arabia"),
    ("SG", "Singapore"),
    ("US", "United States"),
    ("ZA", "South Africa"),
)


def country_choices() -> list[tuple[str, str]]:
    """``[(code, label), ...]`` from ``settings.EMS_COUNTRIES`` (falls back to the default list)."""
    configured = getattr(settings, "EMS_COUNTRIES", None)
    return [(str(code).upper(), str(label)) for code, label in (configured or DEFAULT_COUNTRIES)]


def country_codes() -> frozenset[str]:
    return frozenset(code for code, _ in country_choices())


def country_label(code: str) -> str:
    code = (code or "").upper()
    return dict(country_choices()).get(code, code)


class Nationality(models.TextChoices):
    """``models.TextChoices`` cannot be built from settings at import time, so nationality uses a
    plain ``CharField`` validated by :func:`validate_nationality` against
    ``settings.EMS_COUNTRIES``. ``NotSpecified`` covers staff who prefer not to declare one."""


NOT_SPECIFIED = ""


def validate_nationality(value: str) -> None:
    code = (value or "").strip().upper()
    if code == NOT_SPECIFIED or code in country_codes():
        return
    raise ValidationError(
        "Choose a nationality from the configured list.", code="unknown_nationality"
    )


class Gender(models.TextChoices):
    """Controlled gender vocabulary.

    ``Other`` and ``Prefer not to say`` exist so the field never forces a binary answer. The set is
    reference data, not free text, and it is enforced by a database ``CHECK`` constraint.
    """

    MALE = "male", "Male"
    FEMALE = "female", "Female"
    OTHER = "other", "Other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"


def gender_choices(allow_blank: bool = True) -> list[tuple[str, str]]:
    """``Gender`` choices, optionally with an empty choice for "not declared"."""
    return [("", "Not declared"), *Gender.choices] if allow_blank else list(Gender.choices)


def display_gender(value: str) -> str:
    return dict(gender_choices()).get(value or "", "Not declared")


class RelationshipType(models.TextChoices):
    """Family / personal relationship between two ``Person`` records.

    Not fixed forever: extend this enum (one line + migration) rather than adding a
    ``father_name``-style column, and the data-quality check still validates stored values.
    """

    SPOUSE = "spouse", "Spouse"
    PARTNER = "partner", "Partner"
    PARENT = "parent", "Parent"
    CHILD = "child", "Child"
    SIBLING = "sibling", "Sibling"
    GUARDIAN = "guardian", "Guardian"
    OTHER = "other", "Other"

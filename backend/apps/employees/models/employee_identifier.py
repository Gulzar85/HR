"""``EmployeeIdentifier`` - official identity documents (CNIC, passport, ...).

Security-critical. A national identifier is **sensitive personal data**, so:

* visibility is gated by ``employees.view_identifiers`` (and read access is audited);
* :attr:`EmployeeIdentifier.masked_value` is what unauthorized viewers and list pages see;
* audit records state *that* an identifier changed, never the old and new values (ADR-021).

Uniqueness (docs/security/employee-data.md): ``(identifier_type, issuing_country, normalized_value)``
for every row that is not ``rejected``. Keying on the country keeps passport numbers from different
issuers apart while still making one CNIC unique across the company. Rejected rows are excluded so a
failed verification can be re-entered and corrected.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from ..validators import validate_issuing_country
from .base import IDENTIFIERS, EmployeeOwnedRecord

# Separators that carry no meaning in an identifier and must not affect uniqueness.
_STRIP = re.compile(r"[\s\-/]")


def normalize_identifier(value: str) -> str:
    """Upper-case, separator-free form used for uniqueness and lookup (CNIC / passport)."""
    return _STRIP.sub("", (value or "").upper())


class IdentifierType(models.TextChoices):
    CNIC = "cnic", "CNIC (national identity card)"
    PASSPORT = "passport", "Passport"
    NATIONAL_ID = "national_id", "National ID"
    DRIVING_LICENCE = "driving_licence", "Driving licence"
    NICOP = "nicop", "NICOP / NCCOP"
    OTHER = "other", "Other official identifier"


#: Identifier types whose value must never be shown unmasked to users lacking
#: ``employees.view_sensitive_identity``, even if they hold ``employees.view_identifiers``.
ALWAYS_SENSITIVE_TYPES = frozenset({IdentifierType.CNIC, IdentifierType.NICOP})


class VerificationStatus(models.TextChoices):
    """Internal verification state. No external identity verification is wired up in Phase 3 -
    this phase establishes the data model and the internal workflow foundation only."""

    UNVERIFIED = "unverified", "Unverified"
    VERIFIED = "verified", "Verified"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"


#: Statuses an identifier can move to while it is still usable for lookups.
OPEN_VERIFICATION_STATUSES = frozenset({VerificationStatus.UNVERIFIED, VerificationStatus.VERIFIED})


class EmployeeIdentifier(EmployeeOwnedRecord):
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.PROTECT, related_name=IDENTIFIERS
    )
    identifier_type = models.CharField(max_length=20, choices=IdentifierType.choices)
    value = models.CharField(
        max_length=64,
        help_text="As issued. Stored unmasked, but always displayed masked without permission.",
    )
    normalized_value = models.CharField(
        max_length=64, editable=False, help_text="Upper-case, separator-free."
    )
    issuing_country = models.CharField(
        max_length=2, blank=True, validators=[validate_issuing_country]
    )
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=12,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
        db_index=True,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    is_primary = models.BooleanField(
        default=False, help_text="The identifier normally used to look this employee up."
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "employees_identifier"
        ordering = ["-is_primary", "identifier_type", "created_at"]
        indexes = [
            models.Index(
                fields=["identifier_type", "issuing_country", "normalized_value"],
                name="emp_ident_lookup_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "identifier_type"],
                condition=models.Q(is_primary=True),
                name="uniq_employee_primary_identifier_type",
            ),
            models.UniqueConstraint(
                fields=["identifier_type", "issuing_country", "normalized_value"],
                condition=~models.Q(verification_status=VerificationStatus.REJECTED),
                name="uniq_identifier_value_per_country",
            ),
            models.CheckConstraint(
                condition=models.Q(expiry_date__isnull=True)
                | models.Q(issue_date__isnull=True)
                | models.Q(expiry_date__gte=models.F("issue_date")),
                name="employees_identifier_eff_dates",
            ),
            models.CheckConstraint(
                condition=models.Q(verification_status__in=[s.value for s in VerificationStatus]),
                name="employees_identifier_verification_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_identifier_type_display()} · {self.masked_value}"

    def save(self, *args, **kwargs):
        self.normalized_value = normalize_identifier(self.value)
        self.issuing_country = (self.issuing_country or "").upper()
        super().save(*args, **kwargs)

    @property
    def masked_value(self) -> str:
        """``*****-*******-3`` - keep the final character only, never the whole value."""
        raw = self.value or ""
        if len(raw) <= 1:
            return "*" * len(raw)
        return f"{'*' * (len(raw) - 1)}{raw[-1]}"

    @property
    def is_sensitive(self) -> bool:
        return self.identifier_type in ALWAYS_SENSITIVE_TYPES

    @property
    def is_expired(self) -> bool:
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.issue_date and self.expiry_date and self.expiry_date < self.issue_date:
            errors["expiry_date"] = "Expiry date cannot be before the issue date."
        try:
            validate_issuing_country(self.issuing_country)
        except ValidationError as exc:
            errors["issuing_country"] = "; ".join(exc.messages)
        if errors:
            raise ValidationError(errors)

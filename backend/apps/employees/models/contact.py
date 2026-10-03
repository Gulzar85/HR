"""``Contact`` - how to reach the employee.

One structured row per contact point instead of ``phone1``/``phone2``/``email1`` columns: adding a
channel must never mean a migration, and channels carry different validation rules.

``is_primary`` means "the current one of its type", enforced by a partial unique constraint on
``(employee, contact_type)``. There is deliberately no single "the primary contact" across types -
a mobile number and an email address are both primary of their own kind
(docs/architecture/employee-domain.md).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from ..validators import normalize_email, normalize_phone, validate_phone
from .base import CONTACTS, EmployeeOwnedRecord


class ContactType(models.TextChoices):
    MOBILE = "mobile", "Mobile"
    PHONE = "phone", "Phone (landline)"
    EMAIL = "email", "Email"
    ALTERNATIVE_EMAIL = "alternative_email", "Alternative email"


EMAIL_TYPES = frozenset({ContactType.EMAIL, ContactType.ALTERNATIVE_EMAIL})
PHONE_TYPES = frozenset({ContactType.MOBILE, ContactType.PHONE})


class Contact(EmployeeOwnedRecord):
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.PROTECT, related_name=CONTACTS
    )
    contact_type = models.CharField(max_length=20, choices=ContactType.choices)
    value = models.CharField(max_length=160)
    normalized_value = models.CharField(max_length=160, editable=False)
    label = models.CharField(
        max_length=60, blank=True, help_text="Optional, e.g. 'work mobile' or 'personal email'."
    )
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(
        default=False, help_text="Set once the owner has confirmed they can be reached on it."
    )

    class Meta:
        db_table = "employees_contact"
        ordering = ["-is_primary", "contact_type", "created_at"]
        indexes = [
            models.Index(
                fields=["contact_type", "normalized_value"], name="emp_contact_lookup_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "contact_type"],
                condition=models.Q(is_primary=True),
                name="uniq_employee_primary_contact_type",
            ),
            models.CheckConstraint(
                condition=models.Q(contact_type__in=[c.value for c in ContactType]),
                name="employees_contact_type_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_contact_type_display()} · {self.value}"

    def save(self, *args, **kwargs):
        self.normalized_value = self.normalize(self.contact_type, self.value)
        super().save(*args, **kwargs)

    @staticmethod
    def normalize(contact_type: str, value: str) -> str:
        return normalize_email(value) if contact_type in EMAIL_TYPES else normalize_phone(value)

    @property
    def is_email(self) -> bool:
        return self.contact_type in EMAIL_TYPES

    def clean(self) -> None:
        super().clean()
        value = (self.value or "").strip()
        if self.is_email:
            if not value:
                raise ValidationError({"value": "An email address is required."})
            # Cheap structural check; the authoritative validation is "can this address receive
            # mail", which only a verification round-trip can answer (is_verified).
            local, _, domain = value.partition("@")
            if not local or not domain or "." not in domain or " " in value:
                raise ValidationError({"value": "Enter a valid email address."})
        elif self.contact_type in PHONE_TYPES:
            validate_phone(value)

"""``EmergencyContact`` - who to call.

An employee may have several; at most one is ``is_primary`` (partial unique constraint on
``employee``), which is the contact used in an incident.

The "relationship to the employee" is a controlled :class:`RelationshipType` value rather than a free
string, so it can be filtered and reported on. The same vocabulary is reused by
:class:`~apps.employees.models.relationship.PersonRelationship`, which records the *other* side as a
first-class ``Person`` when they are known to the system.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from ..validators import validate_phone
from .base import EMERGENCY_CONTACTS, EmployeeOwnedRecord
from .reference import RelationshipType


class EmergencyContact(EmployeeOwnedRecord):
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.PROTECT, related_name=EMERGENCY_CONTACTS
    )
    name = models.CharField(max_length=150)
    relationship = models.CharField(
        max_length=20,
        choices=RelationshipType.choices,
        help_text="How this person is related to the employee.",
    )
    phone = models.CharField(max_length=40)
    alternative_phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "employees_emergency_contact"
        ordering = ["-is_primary", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(is_primary=True),
                name="uniq_employee_primary_emergency_contact",
            ),
            models.CheckConstraint(
                condition=models.Q(relationship__in=[r.value for r in RelationshipType]),
                name="employees_emergency_relationship_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_relationship_display()})"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        for field in ("phone", "alternative_phone"):
            if getattr(self, field):
                try:
                    validate_phone(getattr(self, field))
                except ValidationError as exc:
                    errors[field] = "; ".join(exc.messages)
        if errors:
            raise ValidationError(errors)

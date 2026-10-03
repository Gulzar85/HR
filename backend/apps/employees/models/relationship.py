"""``PersonRelationship`` - a controlled link between two people.

Phase 3 keeps this deliberately thin: one row per declared relationship between two ``Person``
records, typed with :class:`RelationshipType`. That covers spouse / parent / child / sibling /
guardian without a family graph (no recursive structures, no derived inference, no automatic
parent-child mirroring) - see docs/architecture/employee-domain.md for the boundary.

``EmergencyContact.relationship`` answers "how is this person related?" for people who are *not* in
the system as ``Person`` records (a shopkeeper, a friend). When the other party *is* a person, a
``PersonRelationship`` can be recorded as well; the two are independent and never auto-synchronised.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import AuditedModel, UUIDModel

from .reference import RelationshipType


class PersonRelationship(UUIDModel, AuditedModel):
    from_person = models.ForeignKey(
        "employees.Person",
        on_delete=models.PROTECT,
        related_name="relationships_from",
    )
    to_person = models.ForeignKey(
        "employees.Person",
        on_delete=models.PROTECT,
        related_name="relationships_to",
    )
    relationship_type = models.CharField(max_length=20, choices=RelationshipType.choices)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "employees_person_relationship"
        ordering = ["from_person__last_name", "to_person__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_person", "to_person", "relationship_type"],
                name="uniq_person_relationship",
            ),
            models.CheckConstraint(
                condition=~models.Q(from_person=models.F("to_person")),
                name="employees_relationship_not_self",
            ),
            models.CheckConstraint(
                condition=models.Q(relationship_type__in=[r.value for r in RelationshipType]),
                name="employees_relationship_type_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.from_person} → {self.to_person} ({self.get_relationship_type_display()})"

    def clean(self) -> None:
        super().clean()
        if self.from_person_id and self.from_person_id == self.to_person_id:
            raise ValidationError({"to_person": "A person cannot be related to themselves."})

"""``TimelineEntry`` - the employee history foundation (Phase 3).

Phase 3 establishes the *foundation only*. One append-only table collects events from every domain
that touches an employee, so the employee page shows a single chronological history instead of one
section per domain. Future phases (Employment, Assignment, Position, Lifecycle, Recruitment,
Onboarding, Movement, Documents, Offboarding, HR Cases) publish into the same table via
``apps.employees.services.timeline_service.record_event`` and set ``source_app`` to their own label.

Design notes
------------
* **Generic on purpose.** ``event_type`` + JSON ``payload`` means a later phase can record its own
  events without a migration to this table.
* **Privacy by default.** ``is_sensitive`` entries are hidden from the UI and the API unless the
  requester holds ``employees.view_sensitive_identity``.
* **Never carries the sensitive value.** Payload fields are safe to display (an identifier change
  records the *type*, not the CNIC).
* **Best effort.** A timeline write must never break the business operation that triggered it, so
  :func:`~apps.employees.services.timeline_service.record_event` swallows and logs failures.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import UUIDModel


class TimelineEntry(UUIDModel):
    """One immutable point on an employee's history."""

    class EventType(models.TextChoices):
        EMPLOYEE_CREATED = "employee_created", "Employee created"
        EMPLOYEE_UPDATED = "employee_updated", "Employee record updated"
        EMPLOYEE_STATUS_CHANGED = "employee_status_changed", "Status changed"
        EMPLOYEE_ARCHIVED = "employee_archived", "Employee archived"
        EMPLOYEE_REACTIVATED = "employee_reactivated", "Employee reactivated"
        PERSON_UPDATED = "person_updated", "Personal details updated"
        PHOTO_REMOVED = "photo_removed", "Profile photo removed"
        IDENTIFIER_ADDED = "identifier_added", "Identifier added"
        IDENTIFIER_UPDATED = "identifier_updated", "Identifier updated"
        IDENTIFIER_VERIFICATION_CHANGED = (
            "identifier_verification_changed",
            "Identifier verification changed",
        )
        IDENTIFIER_VIEWED = "identifier_viewed", "Sensitive identifier viewed"
        CONTACT_ADDED = "contact_added", "Contact added"
        CONTACT_UPDATED = "contact_updated", "Contact updated"
        CONTACT_REMOVED = "contact_removed", "Contact removed"
        ADDRESS_ADDED = "address_added", "Address added"
        ADDRESS_CHANGED = "address_changed", "Address changed"
        ADDRESS_ENDED = "address_ended", "Previous address closed"
        EMERGENCY_CONTACT_ADDED = "emergency_contact_added", "Emergency contact added"
        EMERGENCY_CONTACT_UPDATED = "emergency_contact_updated", "Emergency contact updated"
        EMERGENCY_CONTACT_REMOVED = "emergency_contact_removed", "Emergency contact removed"
        RELATIONSHIP_ADDED = "relationship_added", "Relationship added"
        RELATIONSHIP_REMOVED = "relationship_removed", "Relationship removed"
        NOTE_ADDED = "note_added", "Note added"
        NOTE_REMOVED = "note_removed", "Note removed"
        USER_LINKED = "user_linked", "User account linked"
        USER_UNLINKED = "user_unlinked", "User account unlinked"

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.PROTECT, related_name="timeline"
    )
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    summary = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    is_sensitive = models.BooleanField(
        default=False,
        help_text="Require employees.view_sensitive_identity to see this entry.",
    )
    source_app = models.CharField(
        max_length=40,
        default="employees",
        help_text="Domain that produced the entry (later phases use their own label).",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "employees_timeline"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["employee", "-occurred_at"], name="emp_timeline_time_idx"),
            models.Index(fields=["employee", "event_type"], name="emp_timeline_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.occurred_at:%d-%b-%Y %H:%M} {self.summary}"

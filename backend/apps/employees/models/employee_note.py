"""``EmployeeNote`` - short internal administrative notes.

Phase 3 provides the foundation only: an author (``created_by``), a timestamp, free-text content and
a ``visibility`` that decides who may read it. Formal case handling (HR Cases, Phase 8+) owns
anything that needs workflow, attachments or retention policy - notes are explicitly *not* that.

``visibility``:

``internal``
    Any user who may view the employee.
``restricted``
    Only holders of ``employees.view_sensitive_identity``. Use for anything that would be
    inappropriate in a shared HR file.
"""

from __future__ import annotations

from django.db import models

from .base import NOTES, EmployeeOwnedRecord


class NoteVisibility(models.TextChoices):
    INTERNAL = "internal", "Internal (visible to HR)"
    RESTRICTED = "restricted", "Restricted (sensitive-identity permission required)"


class EmployeeNote(EmployeeOwnedRecord):
    employee = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name=NOTES)
    content = models.TextField()
    visibility = models.CharField(
        max_length=12, choices=NoteVisibility.choices, default=NoteVisibility.INTERNAL
    )
    pinned = models.BooleanField(default=False, help_text="Keep at the top of the notes list.")

    class Meta:
        db_table = "employees_employee_note"
        ordering = ["-pinned", "-created_at"]
        indexes = [
            models.Index(fields=["employee", "visibility"], name="emp_note_emp_vis_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(visibility__in=[v.value for v in NoteVisibility]),
                name="employees_note_visibility_valid",
            ),
        ]

    def __str__(self) -> str:
        preview = " ".join(self.content.split())[:60]
        return f"Note {self.pk} on {self.employee_id}: {preview}"

    @property
    def is_restricted(self) -> bool:
        return self.visibility == NoteVisibility.RESTRICTED

"""``Person`` - the human being (docs/adr/ADR-018).

A ``Person`` is identity only: name, date of birth, gender, nationality, photo. It holds **no**
contact details, addresses, emergency contacts, identifiers or employee codes - those live on their
own models so that one concept owns one table and so that a future recruitment ``HireService`` can
reuse an existing person (docs/architecture/employee-domain.md).

A person may exist with no ``Employee`` record (e.g. a candidate, or a family member referenced by
``PersonRelationship``), which is why the link is optional from this side.
"""

from __future__ import annotations

from django.db import models

from apps.common.models import AuditedModel, UUIDModel

from ..validators import validate_date_of_birth, validate_profile_photo
from .reference import Gender, validate_nationality


class Person(UUIDModel, AuditedModel):
    first_name = models.CharField("first name", max_length=80)
    middle_name = models.CharField("middle name", max_length=80, blank=True)
    last_name = models.CharField("last name", max_length=80)
    preferred_name = models.CharField(
        "preferred name",
        max_length=80,
        blank=True,
        help_text="What the person is actually called. Shown instead of the full name when set.",
    )
    date_of_birth = models.DateField(
        "date of birth",
        null=True,
        blank=True,
        validators=[validate_date_of_birth],
        help_text="Optional. Age is always calculated, never stored.",
    )
    gender = models.CharField(
        max_length=20,
        choices=Gender.choices,
        blank=True,
        help_text="Not declared is a valid answer.",
    )
    nationality = models.CharField(
        max_length=2,
        blank=True,
        validators=[validate_nationality],
        help_text="ISO 3166-1 alpha-2 code from the configured country list.",
    )
    profile_photo = models.ImageField(
        "profile photo",
        upload_to="employees/photos/%Y/%m/",
        blank=True,
        validators=[validate_profile_photo],
        help_text="Optional. JPEG, PNG, GIF or WEBP.",
    )

    class Meta:
        db_table = "employees_person"
        ordering = ["last_name", "first_name", "pk"]
        indexes = [
            # Supports the list default ordering (last_name, first_name) and surname lookups.
            models.Index(fields=["last_name", "first_name"], name="emp_person_name_idx"),
            # Gender is a supported list filter, so it is indexed on its own.
            models.Index(fields=["gender"], name="emp_person_gender_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(gender__in=["", *[g.value for g in Gender]]),
                name="employees_person_gender_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(nationality="") | models.Q(nationality__regex=r"^[A-Z]{2}$"),
                name="employees_person_nationality_code",
            ),
        ]

    def __str__(self) -> str:
        return self.display_name

    # ------------------------------------------------------------------ display helpers
    @property
    def full_name(self) -> str:
        """Structured name joined for display. Computed, never stored (no redundant column)."""
        return " ".join(
            part for part in (self.first_name, self.middle_name, self.last_name) if part
        ).strip()

    @property
    def display_name(self) -> str:
        """Preferred name when set, otherwise the full name."""
        return self.preferred_name or self.full_name

    @property
    def initials(self) -> str:
        parts = [p for p in (self.first_name, self.last_name) if p]
        return "".join(p[0].upper() for p in parts)[:2] or "?"

    @property
    def age(self) -> int | None:
        """Completed years old today, or ``None`` when the date of birth is unknown."""
        from ..validators import age_on

        return age_on(self.date_of_birth) if self.date_of_birth else None

    @property
    def employee_record(self):
        """The ``Employee`` for this person, or ``None``. Never raises (reverse one-to-one)."""
        return getattr(self, "employee", None)

    def replace_photo(self, uploaded) -> None:
        """Swap in a new photo; the superseded file is deleted so storage does not grow forever."""
        previous = self.profile_photo
        self.profile_photo = uploaded or None
        if previous:
            self._delete_photo_file(previous)

    def delete_photo(self) -> None:
        previous, self.profile_photo = self.profile_photo, None
        if previous:
            self._delete_photo_file(previous)

    @staticmethod
    def _delete_photo_file(field_file) -> None:
        from apps.common.logging import get_logger

        try:
            field_file.storage.delete(field_file.name)
        except Exception:  # noqa: BLE001 - losing a file must never break the request
            get_logger("app").warning(
                "profile_photo_delete_failed", extra={"name": str(field_file.name)}
            )

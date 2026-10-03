"""``Address`` - where the employee lives.

Address columns live here once, never copied into ``Employee`` or ``Person`` (Phase 3 rule: one
concept, one table).

History (docs/architecture/employee-domain.md): addresses are **effective-dated**, not overwritten.
When the address of a given type changes, ``AddressService`` closes the previous row's
``effective_to`` and opens a new one, so "where did this employee live in March?" stays answerable.
``effective_to`` is the last day the address applied (inclusive); ``NULL`` means current. This is a
deliberately simple temporal model - no interval tables, no exclusion constraints.

``is_primary`` marks the current row of its ``address_type`` (partial unique constraint), which is
what the list and detail screens read.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from ..validators import validate_issuing_country
from .base import ADDRESSES, EmployeeOwnedRecord


class AddressType(models.TextChoices):
    CURRENT = "current", "Current address"
    PERMANENT = "permanent", "Permanent address"
    OTHER = "other", "Other address"


class Address(EmployeeOwnedRecord):
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.PROTECT, related_name=ADDRESSES
    )
    address_type = models.CharField(max_length=12, choices=AddressType.choices)
    address_line_1 = models.CharField("address line 1", max_length=200)
    address_line_2 = models.CharField("address line 2", max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state_province = models.CharField("state / province", max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, blank=True, validators=[validate_issuing_country])
    is_primary = models.BooleanField(default=False, help_text="The current address of its type.")
    effective_from = models.DateField(
        null=True, blank=True, help_text="Defaults to today when the address is recorded."
    )
    effective_to = models.DateField(
        null=True,
        blank=True,
        help_text="Last day this address applied (inclusive). Empty means current.",
    )

    class Meta:
        db_table = "employees_address"
        ordering = ["-is_primary", "-effective_from", "created_at"]
        indexes = [
            models.Index(fields=["address_type", "is_primary"], name="emp_address_type_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "address_type"],
                condition=models.Q(is_primary=True),
                name="uniq_employee_primary_address_type",
            ),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True)
                | models.Q(effective_from__isnull=True)
                | models.Q(effective_to__gte=models.F("effective_from")),
                name="employees_address_eff_dates",
            ),
            models.CheckConstraint(
                condition=models.Q(address_type__in=[a.value for a in AddressType]),
                name="employees_address_type_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_address_type_display()} · {self.city}"

    def save(self, *args, **kwargs):
        self.country = (self.country or "").upper()
        super().save(*args, **kwargs)

    @property
    def is_current(self) -> bool:
        from apps.common.utils import today_local

        today = today_local()
        started = self.effective_from is None or self.effective_from <= today
        ended = self.effective_to is None or self.effective_to >= today
        return started and ended

    @property
    def one_line(self) -> str:
        parts = [
            self.address_line_1,
            self.address_line_2,
            self.city,
            self.state_province,
            self.postal_code,
        ]
        return ", ".join(p for p in parts if p)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            errors["effective_to"] = "The end date cannot be before the start date."
        try:
            validate_issuing_country(self.country)
        except ValidationError as exc:
            errors["country"] = "; ".join(exc.messages)
        if errors:
            raise ValidationError(errors)

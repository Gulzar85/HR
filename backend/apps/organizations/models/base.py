"""Shared abstract base for organization units.

Every unit has a UUID primary key, an immutable human-readable ``code``, a name, a meaningful
``status`` and an effective-date range. ``effective_to`` is the *last* day the unit was effective
(inclusive, NULL = open). Units are never physically deleted (FKs use PROTECT).
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.common.models import BusinessCodeModel, TimeStampedModel, UUIDModel
from apps.common.utils import today_local


class OrgStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    ARCHIVED = "archived", "Archived"


class RestaurantStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    TEMPORARILY_CLOSED = "temporarily_closed", "Temporarily closed"
    CLOSED = "closed", "Closed"
    ARCHIVED = "archived", "Archived"


# Statuses that count as "still operating" for parent/child integrity rules.
LIVE_STATUSES = frozenset({"planned", "active", "temporarily_closed"})


class OrganizationUnit(UUIDModel, TimeStampedModel, BusinessCodeModel):
    ORG_TYPE: ClassVar[str] = ""

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=OrgStatus.choices, default=OrgStatus.ACTIVE, db_index=True
    )
    effective_from = models.DateField(default=today_local)
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True)
                | models.Q(effective_to__gte=models.F("effective_from")),
                name="%(app_label)s_%(class)s_eff_dates",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"

    @property
    def org_type(self) -> str:
        return self.ORG_TYPE

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES


def status_check(model_name: str, choices: type[models.TextChoices]) -> models.CheckConstraint:
    return models.CheckConstraint(
        condition=models.Q(status__in=[c.value for c in choices]),
        name=f"organizations_{model_name}_status_valid",
    )

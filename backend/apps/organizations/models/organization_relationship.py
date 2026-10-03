"""Effective-dated parent relationships: the historical record of the hierarchy.

The FK on each unit (e.g. ``Restaurant.area``) is the *current* parent; this table keeps every
parent a unit has had, so "which Region did Restaurant X belong to on 2025-06-30?" is answerable.

Intervals are half-open: ``effective_from`` inclusive, ``effective_to`` **exclusive** (NULL = current).
A move on date D closes the old row at D and opens a new row from D (no gaps, no overlaps).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class OrganizationRelationship(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    child_type = models.CharField(max_length=32)
    child_id = models.UUIDField()
    parent_type = models.CharField(max_length=32)
    parent_id = models.UUIDField()
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["child_type", "child_id", "effective_from"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True)
                | models.Q(effective_to__gte=models.F("effective_from")),
                name="org_rel_dates",
            ),
            models.UniqueConstraint(
                fields=["child_type", "child_id"],
                condition=models.Q(effective_to__isnull=True),
                name="org_rel_one_current_parent",
            ),
        ]
        indexes = [
            models.Index(
                fields=["child_type", "child_id", "effective_from"], name="org_rel_child_idx"
            ),
            models.Index(fields=["parent_type", "parent_id"], name="org_rel_parent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.child_type}:{self.child_id} -> {self.parent_type}:{self.parent_id}"

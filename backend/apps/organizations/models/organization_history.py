from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class OrganizationHistory(models.Model):
    """Business history of an organization unit (who, when, what, before/after, reason).

    Mirrored into the platform AuditLog; this table is the domain-facing timeline.
    """

    class Event(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        RENAMED = "renamed", "Renamed"
        ACTIVATED = "activated", "Activated"
        DEACTIVATED = "deactivated", "Deactivated"
        ARCHIVED = "archived", "Archived"
        MOVED = "moved", "Moved (parent changed)"
        TEMPORARILY_CLOSED = "temporarily_closed", "Temporarily closed"
        CLOSED = "closed", "Closed"
        REOPENED = "reopened", "Reopened"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity_type = models.CharField(max_length=32)
    entity_id = models.UUIDField()
    entity_code = models.CharField(max_length=40)
    event = models.CharField(max_length=24, choices=Event.choices)
    effective_date = models.DateField(null=True, blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name_plural = "organization history"
        indexes = [
            models.Index(
                fields=["entity_type", "entity_id", "-timestamp"], name="org_hist_entity_idx"
            )
        ]

    def __str__(self) -> str:
        return f"{self.entity_code} {self.event}"

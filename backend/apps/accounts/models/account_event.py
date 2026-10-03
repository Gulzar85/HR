from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class AccountEvent(models.Model):
    """Privileged change to a user account (the *target* is ``user``). Mirrored into AuditLog."""

    class EventType(models.TextChoices):
        USER_CREATED = "user_created", "User created"
        USER_UPDATED = "user_updated", "User updated"
        STATUS_CHANGED = "status_changed", "Account status changed"
        ROLE_ASSIGNED = "role_assigned", "Role assigned"
        ROLE_REMOVED = "role_removed", "Role removed"
        GROUP_ADDED = "group_added", "Added to group"
        GROUP_REMOVED = "group_removed", "Removed from group"
        PERMISSION_CHANGED = "permission_changed", "Direct permissions changed"
        SCOPE_GRANTED = "scope_granted", "Scope granted"
        SCOPE_REVOKED = "scope_revoked", "Scope revoked"
        PASSWORD_SET_BY_ADMIN = "password_set_by_admin", "Password set by administrator"
        PASSWORD_RESET_SENT = "password_reset_sent", "Password reset link sent"
        SESSION_REVOKED = "session_revoked", "Session revoked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account_events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["user", "-timestamp"], name="acctevt_user_ts_idx")]

    def __str__(self) -> str:
        return f"{self.event_type} -> {self.user_id}"

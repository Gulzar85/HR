from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class LoginEvent(models.Model):
    """Authentication events. Never stores passwords, tokens, or raw session keys."""

    class EventType(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "Login"
        LOGIN_FAILED = "login_failed", "Failed login"
        LOGOUT = "logout", "Logout"
        PASSWORD_CHANGED = "password_changed", "Password changed"
        PASSWORD_RESET_REQUESTED = "password_reset_requested", "Password reset requested"
        PASSWORD_RESET_COMPLETED = "password_reset_completed", "Password reset completed"
        ACCOUNT_LOCKED = "account_locked", "Account locked"
        ACCOUNT_UNLOCKED = "account_unlocked", "Account unlocked"
        ACCOUNT_ACTIVATED = "account_activated", "Account activated"
        ACCOUNT_DEACTIVATED = "account_deactivated", "Account deactivated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="login_events",
    )
    identifier = models.CharField(
        max_length=254, blank=True, help_text="Email attempted (no secrets)."
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    success = models.BooleanField(default=True)
    failure_reason = models.CharField(max_length=64, blank=True)
    channel = models.CharField(max_length=10, default="web")  # web | api | admin
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    session_ref = models.CharField(
        max_length=16, blank=True, help_text="Truncated hash, not the key."
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "-timestamp"], name="loginevt_user_ts_idx"),
            models.Index(fields=["event_type", "-timestamp"], name="loginevt_type_ts_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.identifier or self.user_id}"

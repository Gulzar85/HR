from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class UserSession(models.Model):
    """Metadata for a web (Django) session so it can be listed and revoked.

    The session secret itself lives only in ``django.contrib.sessions``; this table stores the key
    (never exposed in UI/API - clients see ``id``). Requires the DB session backend.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="web_sessions"
    )
    session_key = models.CharField(max_length=40, unique=True, editable=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "revoked_at"], name="usersession_user_rev_idx")]

    def __str__(self) -> str:
        return f"session {self.pk} of {self.user_id}"

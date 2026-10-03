"""Generic access scope: *where* a user's permissions apply.

A scope is ``(scope_type, scope_ref)``. ``scope_type`` is a string registered in
``apps.accounts.services.scope_service`` (company, region, area, restaurant, ...) and
``scope_ref`` is the referenced object's id/code **as text**. There is deliberately no foreign key
to any organization model: Phase 2 registers its types and (optionally) a hierarchy expander, and
Phase 1 data/code stay unchanged.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserScope(models.Model):
    GLOBAL_REF = "*"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scopes"
    )
    scope_type = models.CharField(max_length=40)
    scope_ref = models.CharField(max_length=64)
    include_descendants = models.BooleanField(
        default=True,
        help_text="Also covers units below this one (resolved by the Organization domain).",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    granted_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "scope_type", "scope_ref"], name="uniq_user_scope"
            )
        ]
        indexes = [models.Index(fields=["scope_type", "scope_ref"], name="scope_type_ref_idx")]

    def __str__(self) -> str:
        return f"{self.scope_type}:{self.scope_ref}"

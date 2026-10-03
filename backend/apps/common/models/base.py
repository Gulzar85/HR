"""Small, composable abstract bases. Models opt in to exactly what they need."""

import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
    """UUID technical primary key. Human-readable identifiers are separate ``code`` fields."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class AuditedModel(TimeStampedModel):
    """Adds who created/updated. Services set these explicitly; no thread-local magic."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    class Meta:
        abstract = True


class ActiveModel(models.Model):
    """Simple active/inactive flag. Use a dedicated status field where a lifecycle exists."""

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True

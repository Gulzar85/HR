from django.conf import settings
from django.db import models

from apps.common.models import UUIDModel


class AuditLog(UUIDModel):
    """Append-only record of who did what to which object. Full audit design: Phase 20."""

    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["object_type", "object_id"], name="audit_object_idx")]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type}:{self.object_id}"

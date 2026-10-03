from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class OutboxEvent(UUIDModel, TimeStampedModel):
    """Event written in the same DB transaction as the business change; delivered by a worker."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    event_type = models.CharField(max_length=100)
    aggregate_type = models.CharField(max_length=100, blank=True)
    aggregate_id = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "available_at"], name="outbox_status_avail_idx")]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.event_type} [{self.status}]"

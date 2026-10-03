"""Outbox write + dispatch logic.

``enqueue_outbox_event`` must be called inside the business transaction: if the transaction
rolls back, the event never exists; if it commits, the event is guaranteed to be delivered.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.common.logging import get_logger
from apps.events import DomainEvent, event_bus

from .models import OutboxEvent

logger = get_logger("celery")
MAX_ATTEMPTS = 5


def enqueue_outbox_event(
    event: DomainEvent | None = None,
    *,
    event_type: str | None = None,
    payload: dict[str, Any] | None = None,
    aggregate_type: str = "",
    aggregate_id: str = "",
) -> OutboxEvent:
    if event is not None:
        event_type = event.event_type
        payload = event.payload()
    if not event_type:
        raise ValueError("event_type is required")
    return OutboxEvent.objects.create(
        event_type=event_type,
        payload=payload or {},
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        available_at=timezone.now(),
    )


def dispatch_pending(batch_size: int = 100) -> dict[str, int]:
    """Deliver due events to the in-process bus. Safe to run from several workers."""
    done = failed = 0
    with transaction.atomic():
        due = (
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(status=OutboxEvent.Status.PENDING, available_at__lte=timezone.now())
            .order_by("created_at")[:batch_size]
        )
        for evt in due:
            try:
                event_bus.publish(evt.event_type, evt.payload)
            except Exception as exc:  # handler failure must not lose the event
                evt.attempts += 1
                evt.last_error = str(exc)[:2000]
                if evt.attempts >= MAX_ATTEMPTS:
                    evt.status = OutboxEvent.Status.FAILED
                else:
                    evt.available_at = timezone.now() + timedelta(seconds=2**evt.attempts * 5)
                failed += 1
                logger.exception("outbox_delivery_failed", extra={"outbox_id": str(evt.id)})
            else:
                evt.status = OutboxEvent.Status.PROCESSED
                evt.processed_at = timezone.now()
                done += 1
            evt.save()
    return {"processed": done, "failed": failed}

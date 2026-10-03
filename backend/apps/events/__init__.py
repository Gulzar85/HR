"""In-process domain event bus (see docs/architecture/events-outbox.md)."""

from .base import DomainEvent
from .bus import event_bus, subscribe

__all__ = ["DomainEvent", "event_bus", "subscribe"]

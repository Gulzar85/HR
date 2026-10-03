"""Minimal synchronous publish/subscribe registry keyed by event_type string.

Handlers must be idempotent: the outbox delivers at-least-once.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from apps.common.logging import get_logger

logger = get_logger("app")

Handler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Handler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def publish(self, event_type: str, payload: dict[str, Any]) -> int:
        """Invoke handlers; exceptions propagate so the caller (outbox) can retry."""
        handlers = list(self._handlers.get(event_type, ()))
        for handler in handlers:
            handler(payload)
        return len(handlers)

    def clear(self) -> None:
        self._handlers.clear()


event_bus = EventBus()


def subscribe(event_type: str) -> Callable[[Handler], Handler]:
    """Decorator: ``@subscribe("employee.transferred")``."""

    def decorator(handler: Handler) -> Handler:
        event_bus.subscribe(event_type, handler)
        return handler

    return decorator

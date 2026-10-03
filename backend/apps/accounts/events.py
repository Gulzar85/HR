"""Domain events emitted by the identity domain (delivered via the outbox; payload = ids only).

Notifications (Phase 14) subscribe with ``@subscribe(UserCreated.event_type)``. No handlers exist yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.events import DomainEvent


@dataclass(frozen=True)
class _UserEvent(DomainEvent):
    user_id: str = ""


@dataclass(frozen=True)
class UserCreated(_UserEvent):
    event_type = "accounts.user_created"


@dataclass(frozen=True)
class UserActivated(_UserEvent):
    event_type = "accounts.user_activated"


@dataclass(frozen=True)
class UserDeactivated(_UserEvent):
    event_type = "accounts.user_deactivated"


@dataclass(frozen=True)
class PasswordChanged(_UserEvent):
    event_type = "accounts.password_changed"

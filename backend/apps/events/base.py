"""Domain event base class.

Concrete events (EmployeeCreated, EmployeeTransferred, ApprovalApproved, ...) are defined by
their owning domain app in later phases, as frozen dataclasses subclassing ``DomainEvent``.
Payloads must be JSON-serialisable and carry identifiers (UUID/code), never model instances.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar


@dataclass(frozen=True)
class DomainEvent:
    event_type: ClassVar[str] = "domain.event"

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    actor_id: str | None = None

    def payload(self) -> dict[str, Any]:
        return asdict(self)

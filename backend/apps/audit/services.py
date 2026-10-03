from __future__ import annotations

from typing import Any

from apps.common.logging import get_logger

from .models import AuditLog

logger = get_logger("audit")


def record_audit(
    *,
    action: str,
    actor: Any = None,
    obj_type: str = "",
    obj_id: str = "",
    changes: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Write an audit row (call inside the business transaction) and emit an audit log line."""
    entry = AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        action=action,
        object_type=obj_type,
        object_id=str(obj_id),
        changes=changes or {},
        ip_address=ip_address,
    )
    logger.info(
        "audit", extra={"action": action, "object_type": obj_type, "object_id": str(obj_id)}
    )
    return entry

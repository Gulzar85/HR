"""Organization history + audit recording (one place, used by every organization service)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from apps.audit.services import record_audit
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext

from ..hierarchy import org_type_of
from ..models import OrganizationHistory


def jsonable(value: Any) -> Any:
    if isinstance(value, date | Decimal):
        return str(value)
    if hasattr(value, "pk") and hasattr(value, "code"):
        return value.code
    return value


def snapshot(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: jsonable(getattr(obj, f)) for f in fields}


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    changed = [k for k in after if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in changed}, {k: after[k] for k in changed}


def record_history(
    obj: Any,
    event: str,
    *,
    actor: Any = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
    effective_date: date | None = None,
    ctx: RequestContext = SYSTEM_CONTEXT,
) -> OrganizationHistory:
    t = org_type_of(obj)
    actor = actor if getattr(actor, "pk", None) else None
    entry = OrganizationHistory.objects.create(
        entity_type=t.key,
        entity_id=obj.pk,
        entity_code=obj.code,
        event=event,
        effective_date=effective_date,
        before=before or {},
        after=after or {},
        reason=reason[:255],
        actor=actor,
        ip_address=ctx.ip_address,
    )
    record_audit(
        action=f"organizations.{t.key}_{event}",
        actor=actor,
        obj_type=t.key,
        obj_id=str(obj.pk),
        changes={"before": before or {}, "after": after or {}},
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        reason=reason,
    )
    return entry

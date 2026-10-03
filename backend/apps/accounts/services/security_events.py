"""Single place that writes LoginEvent / AccountEvent rows and mirrors them into the audit log.

Never pass passwords, tokens or session keys to these helpers.
"""

from __future__ import annotations

import hashlib
from typing import Any

from apps.audit.services import record_audit
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext

from ..models import AccountEvent, LoginEvent


def session_ref(session_key: str | None) -> str:
    return hashlib.sha256(session_key.encode()).hexdigest()[:16] if session_key else ""


def record_login_event(
    event_type: str,
    *,
    user: Any = None,
    identifier: str = "",
    success: bool = True,
    failure_reason: str = "",
    channel: str = "web",
    ctx: RequestContext = SYSTEM_CONTEXT,
    session_key: str | None = None,
) -> LoginEvent:
    event = LoginEvent.objects.create(
        user=user if getattr(user, "pk", None) else None,
        identifier=(identifier or getattr(user, "email", ""))[:254],
        event_type=event_type,
        success=success,
        failure_reason=failure_reason,
        channel=channel,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        session_ref=session_ref(session_key),
    )
    record_audit(
        action=f"auth.{event_type}",
        actor=user,
        obj_type="user",
        obj_id=str(getattr(user, "pk", "") or ""),
        changes={"success": success, "reason": failure_reason, "channel": channel},
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
    )
    return event


def record_account_event(
    event_type: str,
    *,
    target: Any,
    actor: Any = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
    ctx: RequestContext = SYSTEM_CONTEXT,
) -> AccountEvent:
    actor = actor if getattr(actor, "pk", None) else None
    event = AccountEvent.objects.create(
        user=target,
        actor=actor,
        event_type=event_type,
        before=before or {},
        after=after or {},
        reason=reason[:255],
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
    )
    record_audit(
        action=f"accounts.{event_type}",
        actor=actor,
        obj_type="user",
        obj_id=str(target.pk),
        changes={"before": before or {}, "after": after or {}},
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        reason=reason,
    )
    return event

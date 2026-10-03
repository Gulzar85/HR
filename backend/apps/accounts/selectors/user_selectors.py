"""Read-side queries for users (no writes). Database-level filtering; no N+1 on list pages."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from apps.audit.models import AuditLog

from ..models import AccountEvent, LoginEvent, User, UserScope


class UserSelector:
    @staticmethod
    def list_users() -> QuerySet[User]:
        return (
            User.objects.defer("password", "preferences")
            .prefetch_related("roles", "groups")
            .order_by("first_name", "last_name", "email")
        )

    @staticmethod
    def get_user(pk: Any) -> User:
        return get_object_or_404(
            User.objects.prefetch_related("roles", "groups", "user_permissions"), pk=pk
        )

    @staticmethod
    def scopes_for(user: User) -> QuerySet[UserScope]:
        return (
            UserScope.objects.filter(user=user)
            .select_related("granted_by")
            .order_by("scope_type", "scope_ref")
        )

    @staticmethod
    def recent_logins(user: User, limit: int = 10) -> QuerySet[LoginEvent]:
        return LoginEvent.objects.filter(user=user).order_by("-timestamp")[:limit]

    @staticmethod
    def recent_audit(user: User, limit: int = 10) -> QuerySet[AuditLog]:
        return AuditLog.objects.filter(object_type="user", object_id=str(user.pk)).select_related(
            "actor"
        )[:limit]

    @staticmethod
    def security_history(user: User, limit: int = 200) -> list[dict[str, Any]]:
        """Login + account events for one user, newest first (merged, bounded)."""
        rows: list[dict[str, Any]] = []
        for e in LoginEvent.objects.filter(user=user).order_by("-timestamp")[:limit]:
            rows.append(
                {
                    "timestamp": e.timestamp,
                    "kind": "authentication",
                    "label": e.get_event_type_display(),
                    "success": e.success,
                    "detail": e.failure_reason.replace("_", " ") if e.failure_reason else "",
                    "actor": None,
                    "ip": e.ip_address,
                    "channel": e.channel,
                }
            )
        qs = (
            AccountEvent.objects.filter(user=user)
            .select_related("actor")
            .order_by("-timestamp")[:limit]
        )
        for a in qs:
            rows.append(
                {
                    "timestamp": a.timestamp,
                    "kind": "account",
                    "label": a.get_event_type_display(),
                    "success": True,
                    "detail": a.reason or _summary(a),
                    "actor": a.actor,
                    "ip": a.ip_address,
                    "channel": "",
                }
            )
        rows.sort(key=lambda r: r["timestamp"], reverse=True)
        return rows[:limit]


def _summary(event: AccountEvent) -> str:
    parts = []
    for side, data in (("from", event.before), ("to", event.after)):
        if data:
            parts.append(f"{side} " + ", ".join(f"{k}={v}" for k, v in data.items()))
    return "; ".join(parts)

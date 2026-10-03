"""Web session tracking and revocation (DB session backend)."""

from __future__ import annotations

from typing import Any

from django.contrib.sessions.models import Session
from django.db.models import QuerySet
from django.utils import timezone

from apps.common.exceptions import NotFoundException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional

from ..models import AccountEvent, User, UserSession
from .security_events import record_account_event


class SessionService:
    @staticmethod
    def register(user: User, session_key: str | None, ctx: RequestContext) -> None:
        if not session_key:
            return
        UserSession.objects.update_or_create(
            session_key=session_key,
            defaults={
                "user": user,
                "ip_address": ctx.ip_address,
                "user_agent": ctx.user_agent,
                "revoked_at": None,
                "revoked_reason": "",
            },
        )

    @staticmethod
    def active_sessions(user: User) -> QuerySet[UserSession]:
        live_keys = Session.objects.filter(expire_date__gt=timezone.now()).values("session_key")
        return UserSession.objects.filter(
            user=user, revoked_at__isnull=True, session_key__in=live_keys
        )

    @staticmethod
    def _terminate(sessions: QuerySet[UserSession], reason: str) -> int:
        keys = list(sessions.values_list("session_key", flat=True))
        Session.objects.filter(session_key__in=keys).delete()
        return sessions.update(revoked_at=timezone.now(), revoked_reason=reason)

    @classmethod
    @transactional
    def revoke_all(
        cls, user: User, *, except_key: str | None = None, reason: str = "revoked"
    ) -> int:
        qs = UserSession.objects.filter(user=user, revoked_at__isnull=True)
        if except_key:
            qs = qs.exclude(session_key=except_key)
        count = cls._terminate(qs, reason)
        cls._blacklist_api_tokens(user)
        return count

    @classmethod
    @transactional
    def revoke_session(
        cls,
        session_id: Any,
        *,
        actor: User,
        owner: User | None = None,
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> UserSession:
        """Revoke one session. ``owner`` restricts the lookup (IDOR guard for self-service)."""
        qs = UserSession.objects.filter(pk=session_id, revoked_at__isnull=True)
        if owner is not None:
            qs = qs.filter(user=owner)
        session = qs.select_related("user").first()
        if session is None:
            raise NotFoundException("Session not found.")
        cls._terminate(UserSession.objects.filter(pk=session.pk), "revoked")
        record_account_event(
            AccountEvent.EventType.SESSION_REVOKED,
            target=session.user,
            actor=actor,
            after={"session_id": str(session.pk)},
            ctx=ctx,
        )
        return session

    @staticmethod
    def rotate_current(user: User, old_key: str | None, new_key: str | None) -> None:
        """Django cycles the session key on password change; keep our row pointing at it."""
        if old_key and new_key and old_key != new_key:
            UserSession.objects.filter(user=user, session_key=old_key).update(session_key=new_key)

    @staticmethod
    def _blacklist_api_tokens(user: User) -> None:
        """Revoke all outstanding API refresh tokens (access tokens expire within minutes)."""
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        for token in OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True):
            BlacklistedToken.objects.get_or_create(token=token)

"""Authentication workflow around Django's auth: lockout policy, login events, password flows.

Passwords are only ever handled through Django (hashers, validators); this module never logs or
stores credentials or reset tokens.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import AuthenticationFailedException, ValidationException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional
from apps.outbox.services import enqueue_outbox_event

from .. import events
from ..models import LoginEvent, User, UserStatus
from ..validators.password import validate_new_password
from .security_events import record_login_event
from .session_service import SessionService

ET = LoginEvent.EventType


def max_failed_logins() -> int:
    return getattr(settings, "EMS_MAX_FAILED_LOGINS", 5)


def lockout_duration() -> timedelta:
    return timedelta(minutes=getattr(settings, "EMS_LOCKOUT_MINUTES", 15))


class AuthenticationService:
    # ------------------------------------------------------------ login outcomes
    @staticmethod
    def record_success(
        user: User, *, ctx: RequestContext, channel: str = "web", session_key: str | None = None
    ) -> None:
        with transaction.atomic():
            if user.failed_login_count:
                User.objects.filter(pk=user.pk).update(failed_login_count=0)
            record_login_event(
                ET.LOGIN_SUCCESS, user=user, ctx=ctx, channel=channel, session_key=session_key
            )
            if channel != "api":
                SessionService.register(user, session_key, ctx)

    @classmethod
    def record_failure(cls, identifier: str, *, ctx: RequestContext, channel: str = "web") -> None:
        """Count the failure, lock the account at the threshold, and record the event."""
        identifier = (identifier or "").strip().lower()
        user = User.objects.filter(email=identifier).first() if identifier else None
        reason = "unknown_user" if user is None else "bad_credentials"
        with transaction.atomic():
            if user is not None:
                locked = User.objects.select_for_update().get(pk=user.pk)
                if locked.status != UserStatus.ACTIVE:
                    reason = f"account_{locked.status}"
                else:
                    locked.failed_login_count += 1
                    locked.save(update_fields=["failed_login_count", "updated_at"])
                    if locked.failed_login_count >= max_failed_logins():
                        from .user_service import UserService

                        UserService.lock(locked, until=timezone.now() + lockout_duration(), ctx=ctx)
                        reason = "locked_out"
            record_login_event(
                ET.LOGIN_FAILED,
                user=user,
                identifier=identifier,
                success=False,
                failure_reason=reason,
                channel=channel,
                ctx=ctx,
            )

    @classmethod
    def api_login(cls, *, request: Any, email: str, password: str, ctx: RequestContext) -> User:
        """Credential check for the token API. Same lockout/event policy as the web login."""
        user = authenticate(request, username=email, password=password)
        if user is None:  # user_login_failed signal already recorded the failure
            raise AuthenticationFailedException("Invalid credentials.", code="invalid_credentials")
        cls.record_success(user, ctx=ctx, channel="api")
        return user

    # --------------------------------------------------------------- passwords
    @classmethod
    @transactional
    def change_password(
        cls,
        *,
        user: User,
        old_password: str,
        new_password: str,
        ctx: RequestContext = SYSTEM_CONTEXT,
        keep_session_key: str | None = None,
    ) -> User:
        user = User.objects.select_for_update().get(pk=user.pk)
        if not user.check_password(old_password):
            raise ValidationException(
                "The current password is incorrect.",
                details={"old_password": ["Incorrect password."]},
            )
        if old_password == new_password:
            raise ValidationException(
                "Choose a different password.",
                details={"new_password": ["Must differ from the current one."]},
            )
        validate_new_password(new_password, user)
        user.set_password(new_password)
        user.password_changed_at = timezone.now()
        user.save(update_fields=["password", "password_changed_at", "updated_at"])
        SessionService.revoke_all(user, except_key=keep_session_key, reason="password_changed")
        record_login_event(ET.PASSWORD_CHANGED, user=user, ctx=ctx)
        enqueue_outbox_event(events.PasswordChanged(user_id=str(user.pk), actor_id=str(user.pk)))
        return user

    @staticmethod
    def record_reset_requested(email: str, ctx: RequestContext) -> None:
        email = (email or "").strip().lower()
        user = User.objects.filter(email=email).first()
        record_login_event(
            ET.PASSWORD_RESET_REQUESTED,
            user=user,
            identifier=email,
            ctx=ctx,
            success=user is not None,
        )

    @classmethod
    @transactional
    def complete_password_reset(cls, user: User, ctx: RequestContext = SYSTEM_CONTEXT) -> User:
        """After Django's reset form saved the new password: end all sessions, activate invites."""
        User.objects.filter(pk=user.pk).update(password_changed_at=timezone.now())
        SessionService.revoke_all(user, reason="password_reset")
        record_login_event(ET.PASSWORD_RESET_COMPLETED, user=user, ctx=ctx)
        enqueue_outbox_event(events.PasswordChanged(user_id=str(user.pk), actor_id=str(user.pk)))
        user.refresh_from_db()
        if user.status == UserStatus.PENDING:
            from .user_service import UserService

            user = UserService.activate(user, actor=None, reason="invitation_accepted", ctx=ctx)
        return user

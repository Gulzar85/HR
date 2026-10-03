"""User account operations and the account status state machine.

    pending --activate--> active --suspend--> suspended --activate--> active
    active --lock--> locked --unlock--> active          (lock is system-initiated by lockout)
    pending|active|suspended|locked --deactivate--> inactive --activate--> active

Every transition: validated, atomic, audited (AccountEvent + AuditLog), emits a domain event via the
outbox, and ends the user's sessions/tokens when the account can no longer sign in.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.db import IntegrityError
from django.utils import timezone

from apps.common.exceptions import BusinessRuleException, ConflictException, ValidationException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional
from apps.common.utils import unique_slug
from apps.outbox.services import enqueue_outbox_event

from .. import events
from ..models import AccountEvent, LoginEvent, Role, User, UserStatus
from ..validators.password import validate_new_password
from ..validators.preferences import clean_preferences
from .email_service import send_account_email
from .guards import assert_can_manage, assert_not_self, authorize
from .role_service import RoleService
from .security_events import record_account_event, record_login_event
from .session_service import SessionService

S = UserStatus

# action -> (allowed source states, target state)
TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "activate": (frozenset({S.PENDING, S.SUSPENDED, S.INACTIVE}), S.ACTIVE),
    "unlock": (frozenset({S.LOCKED}), S.ACTIVE),
    "suspend": (frozenset({S.ACTIVE}), S.SUSPENDED),
    "lock": (frozenset({S.ACTIVE}), S.LOCKED),
    "deactivate": (frozenset({S.PENDING, S.ACTIVE, S.SUSPENDED, S.LOCKED}), S.INACTIVE),
}
_LOGIN_EVENT_FOR = {
    "activate": LoginEvent.EventType.ACCOUNT_ACTIVATED,
    "unlock": LoginEvent.EventType.ACCOUNT_UNLOCKED,
    "lock": LoginEvent.EventType.ACCOUNT_LOCKED,
    "deactivate": LoginEvent.EventType.ACCOUNT_DEACTIVATED,
}
PROFILE_FIELDS = ("first_name", "last_name", "email", "username")


def _snapshot(user: User) -> dict[str, Any]:
    return {f: getattr(user, f) for f in PROFILE_FIELDS}


class UserService:
    # --------------------------------------------------------------- create / update
    @classmethod
    @transactional
    def create_user(
        cls,
        *,
        actor: User | None,
        email: str,
        first_name: str = "",
        last_name: str = "",
        username: str | None = None,
        password: str | None = None,
        roles: Iterable[Role] = (),
        groups: Iterable[Any] = (),
        send_invite: bool = True,
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> User:
        authorize(actor, "accounts.add_user")
        email = email.strip().lower()
        if not email:
            raise ValidationException("An email address is required.")
        if User.objects.filter(email__iexact=email).exists():
            raise ConflictException(
                "A user with this email already exists.", code="duplicate_email"
            )
        if username and User.objects.filter(username__iexact=username).exists():
            raise ConflictException("This username is taken.", code="duplicate_username")
        username = username or unique_slug(
            User.objects.all(), email.split("@")[0], field="username", max_length=150
        )
        user = User(email=email, username=username, first_name=first_name, last_name=last_name)
        if password:
            validate_new_password(password, user)
            user.set_password(password)
            user.password_changed_at = timezone.now()
            user.status = S.ACTIVE
        else:
            user.set_unusable_password()
            user.status = S.PENDING
        user.status_changed_at = timezone.now()
        try:
            user.save()
        except IntegrityError as exc:
            raise ConflictException("A user with this email or username already exists.") from exc

        roles, groups = list(roles), list(groups)
        if actor is not None:
            if roles:
                RoleService.set_user_roles(actor=actor, user=user, roles=roles, ctx=ctx)
            if groups:
                RoleService.set_user_groups(actor=actor, user=user, groups=groups, ctx=ctx)
        else:  # trusted system/seed path
            cls._seed_roles(user, roles)
            user.groups.set(groups)
        record_account_event(
            AccountEvent.EventType.USER_CREATED,
            target=user,
            actor=actor,
            after={**_snapshot(user), "status": user.status},
            ctx=ctx,
        )
        enqueue_outbox_event(events.UserCreated(user_id=str(user.pk), actor_id=_id(actor)))
        if send_invite and user.status == S.PENDING:
            send_account_email("account_activation", user, ctx, with_link=True)
        return user

    @staticmethod
    def _seed_roles(user: User, roles: list[Role]) -> None:
        from ..models import UserRole

        for role in roles:
            UserRole.objects.get_or_create(user=user, role=role)

    @classmethod
    @transactional
    def update_user(
        cls, *, actor: User, user: User, ctx: RequestContext = SYSTEM_CONTEXT, **fields: Any
    ) -> User:
        authorize(actor, "accounts.change_user")
        assert_can_manage(actor, user)
        return cls._apply_profile(actor, user, fields, ctx)

    @classmethod
    @transactional
    def update_own_profile(
        cls, *, user: User, ctx: RequestContext = SYSTEM_CONTEXT, **fields: Any
    ) -> User:
        """Self-service: only names, email and UI preferences (never roles/status/staff flags)."""
        allowed = {"first_name", "last_name", "email", "preferences"}
        if set(fields) - allowed:
            raise ValidationException("These fields cannot be changed here.")
        return cls._apply_profile(user, user, fields, ctx)

    @classmethod
    def _apply_profile(
        cls, actor: User, user: User, fields: dict[str, Any], ctx: RequestContext
    ) -> User:
        user = User.objects.select_for_update().get(pk=user.pk)
        before = _snapshot(user)
        if "email" in fields:
            email = fields["email"].strip().lower()
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                raise ConflictException(
                    "A user with this email already exists.", code="duplicate_email"
                )
            fields["email"] = email
        if fields.get("username") and (
            User.objects.filter(username__iexact=fields["username"]).exclude(pk=user.pk).exists()
        ):
            raise ConflictException("This username is taken.", code="duplicate_username")
        prefs_changed = False
        for name, value in fields.items():
            if name == "preferences":
                value = clean_preferences(value)
                prefs_changed = value != user.preferences
                user.preferences = value
            elif name in PROFILE_FIELDS:
                setattr(user, name, value)
        user.save()
        after = _snapshot(user)
        if before != after or prefs_changed:
            record_account_event(
                AccountEvent.EventType.USER_UPDATED,
                target=user,
                actor=actor,
                before={k: v for k, v in before.items() if before[k] != after[k]},
                after={k: v for k, v in after.items() if before[k] != after[k]}
                | ({"preferences": user.preferences} if prefs_changed else {}),
                ctx=ctx,
            )
        return user

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    @transactional
    def _transition(
        cls,
        action: str,
        user: User,
        *,
        actor: User | None,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
        locked_until: datetime | None = None,
    ) -> User:
        if actor is not None:
            authorize(actor, "accounts.manage_users")
            assert_can_manage(actor, user)
            if action in {"suspend", "deactivate", "lock"}:
                assert_not_self(actor, user, "You cannot suspend or deactivate your own account.")
        user = User.objects.select_for_update().get(pk=user.pk)
        sources, target = TRANSITIONS[action]
        if user.status not in sources:
            raise BusinessRuleException(
                f"Cannot {action} an account that is {user.get_status_display().lower()}.",
                code="invalid_status_transition",
            )
        before = user.status
        user.status = target
        user.status_reason = reason[:255]
        user.status_changed_at = timezone.now()
        user.failed_login_count = 0
        user.locked_until = locked_until if target == S.LOCKED else None
        user.save()

        record_account_event(
            AccountEvent.EventType.STATUS_CHANGED,
            target=user,
            actor=actor,
            before={"status": before},
            after={"status": target},
            reason=reason,
            ctx=ctx,
        )
        if action in _LOGIN_EVENT_FOR:
            record_login_event(_LOGIN_EVENT_FOR[action], user=user, ctx=ctx, success=True)
        if target != S.ACTIVE:
            SessionService.revoke_all(user, reason=action)
        if action == "activate":
            enqueue_outbox_event(events.UserActivated(user_id=str(user.pk), actor_id=_id(actor)))
        elif action == "deactivate":
            enqueue_outbox_event(events.UserDeactivated(user_id=str(user.pk), actor_id=_id(actor)))
            send_account_email("account_deactivation", user, ctx)
        return user

    @classmethod
    def activate(
        cls,
        user: User,
        *,
        actor: User | None,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ):
        return cls._transition("activate", user, actor=actor, reason=reason, ctx=ctx)

    @classmethod
    def deactivate(
        cls,
        user: User,
        *,
        actor: User | None,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ):
        return cls._transition("deactivate", user, actor=actor, reason=reason, ctx=ctx)

    @classmethod
    def suspend(
        cls,
        user: User,
        *,
        actor: User | None,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ):
        return cls._transition("suspend", user, actor=actor, reason=reason, ctx=ctx)

    @classmethod
    def unlock(
        cls,
        user: User,
        *,
        actor: User | None,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ):
        return cls._transition("unlock", user, actor=actor, reason=reason, ctx=ctx)

    @classmethod
    def lock(
        cls,
        user: User,
        *,
        until: datetime,
        reason: str = "too_many_failed_logins",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ):
        """System-initiated (lockout policy); no human actor."""
        return cls._transition("lock", user, actor=None, reason=reason, ctx=ctx, locked_until=until)

    @classmethod
    def apply_action(
        cls, user: User, action: str, *, actor: User, reason: str = "", ctx=SYSTEM_CONTEXT
    ):
        """Dispatch for UI/API: only human-initiated actions (lock is system-only)."""
        if action not in {"activate", "deactivate", "suspend", "unlock"}:
            raise ValidationException(f"Unknown action '{action}'.")
        return getattr(cls, action)(user, actor=actor, reason=reason, ctx=ctx)

    # ------------------------------------------------------------------ passwords
    @classmethod
    @transactional
    def set_password_by_admin(
        cls, *, actor: User, user: User, password: str, ctx: RequestContext = SYSTEM_CONTEXT
    ) -> User:
        authorize(actor, "accounts.manage_users")
        assert_not_self(actor, user, "Use 'Change password' in your profile for your own account.")
        assert_can_manage(actor, user)
        validate_new_password(password, user)
        user.set_password(password)
        user.password_changed_at = timezone.now()
        user.save(update_fields=["password", "password_changed_at", "updated_at"])
        SessionService.revoke_all(user, reason="password_set_by_admin")
        record_account_event(
            AccountEvent.EventType.PASSWORD_SET_BY_ADMIN, target=user, actor=actor, ctx=ctx
        )
        return user

    @classmethod
    @transactional
    def send_password_reset(
        cls, *, actor: User, user: User, ctx: RequestContext = SYSTEM_CONTEXT
    ) -> None:
        authorize(actor, "accounts.manage_users")
        assert_can_manage(actor, user)
        if user.status in (S.INACTIVE, S.SUSPENDED):
            raise BusinessRuleException("Reactivate the account before sending a reset link.")
        template = "account_activation" if user.status == S.PENDING else "password_reset"
        send_account_email(template, user, ctx, with_link=True)
        record_account_event(
            AccountEvent.EventType.PASSWORD_RESET_SENT, target=user, actor=actor, ctx=ctx
        )


def _id(user: User | None) -> str | None:
    return str(user.pk) if user else None

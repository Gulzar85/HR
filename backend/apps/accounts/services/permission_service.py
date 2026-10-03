"""Central "can this user do X?" API. Future apps call this - never inspect raw User fields.

Permission names follow Django's ``app_label.codename`` and the convention in
docs/security/authorization.md (``employees.view_employee``, ``recruitment.manage_offer`` ...).
Superusers pass checks (Django semantics) but every privileged *change* is still audited.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.contrib.auth.models import Group, Permission
from django.db.models import Model, QuerySet
from guardian.shortcuts import assign_perm, get_objects_for_user, remove_perm

from apps.common.exceptions import PermissionDeniedException, ValidationException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional

from ..models import AccountEvent, User
from .security_events import record_account_event

EXCLUDED_APPS = {
    "admin",
    "contenttypes",
    "sessions",
    "guardian",
    "import_export",
    "token_blacklist",
    "outbox",
}
# Internal models: managed only through services, never granted as raw add/change/delete.
EXCLUDED_MODELS = {
    ("auth", "permission"),
    ("auth", "group"),  # groups are administered through accounts.manage_roles
    ("accounts", "userrole"),
    ("accounts", "userscope"),
    ("accounts", "usersession"),
    ("accounts", "groupprofile"),
    ("common", "codesequence"),
}
# Append-only records: only "view" can be granted.
READ_ONLY_MODELS = {("accounts", "loginevent"), ("accounts", "accountevent"), ("audit", "auditlog")}


def perm_label(p: Permission) -> str:
    return f"{p.content_type.app_label}.{p.codename}"


class PermissionService:
    # --- checks ------------------------------------------------------------------
    @staticmethod
    def can(user: Any, permission: str, obj: Model | None = None) -> bool:
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return bool(user.has_perm(permission, obj))

    @classmethod
    def require(cls, user: Any, permission: str, obj: Model | None = None) -> None:
        if not cls.can(user, permission, obj):
            raise PermissionDeniedException()

    @staticmethod
    def effective_permissions(user: User) -> list[str]:
        """Union of direct, group and role permissions (sorted). Empty for inactive users."""
        return sorted(user.get_all_permissions())

    @staticmethod
    def assignable_permissions() -> QuerySet[Permission]:
        qs = Permission.objects.exclude(content_type__app_label__in=EXCLUDED_APPS)
        for app, model in EXCLUDED_MODELS:
            qs = qs.exclude(content_type__app_label=app, content_type__model=model)
        for app, model in READ_ONLY_MODELS:
            qs = qs.exclude(
                content_type__app_label=app,
                content_type__model=model,
                codename__regex=r"^(add|change|delete)_",
            )
        return qs.select_related("content_type").order_by(
            "content_type__app_label", "content_type__model", "codename"
        )

    @classmethod
    def assert_can_grant(cls, actor: User | None, permissions: Iterable[Permission]) -> None:
        """Privilege-escalation guard: you cannot hand out permissions you do not hold."""
        if actor is None or actor.is_superuser:
            return
        held = set(actor.get_all_permissions())
        missing = sorted({perm_label(p) for p in permissions} - held)
        if missing:
            raise PermissionDeniedException(
                "You cannot grant permissions you do not hold.", details={"permissions": missing}
            )

    # --- direct user permissions (discouraged in favour of roles; kept for exceptions) ---
    @classmethod
    @transactional
    def set_user_permissions(
        cls,
        *,
        actor: User,
        user: User,
        permissions: Iterable[Permission],
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> User:
        if actor.pk == user.pk:
            raise PermissionDeniedException("You cannot change your own permissions.")
        perms = list(permissions)
        cls.assert_can_grant(actor, perms)
        before = sorted(perm_label(p) for p in user.user_permissions.select_related("content_type"))
        user.user_permissions.set(perms)
        after = sorted(perm_label(p) for p in perms)
        if before != after:
            record_account_event(
                AccountEvent.EventType.PERMISSION_CHANGED,
                target=user,
                actor=actor,
                before={"permissions": before},
                after={"permissions": after},
                reason=reason,
                ctx=ctx,
            )
        return user

    # --- object-level permissions (django-guardian) -------------------------------
    @staticmethod
    def grant_object_permission(subject: User | Group, permission: str, obj: Model) -> None:
        assign_perm(permission, subject, obj)

    @staticmethod
    def revoke_object_permission(subject: User | Group, permission: str, obj: Model) -> None:
        remove_perm(permission, subject, obj)

    @classmethod
    def can_access_object(cls, user: Any, permission: str, obj: Model) -> bool:
        """Model-level permission OR object-level grant (guardian)."""
        return cls.can(user, permission, obj) or cls.can(user, permission)

    @staticmethod
    def objects_for_user(user: User, permission: str, queryset: QuerySet) -> QuerySet:
        """Rows of ``queryset`` the user holds ``permission`` on (object-level or model-level)."""
        return get_objects_for_user(user, permission, klass=queryset, accept_global_perms=True)

    @staticmethod
    def resolve_permissions(labels: Iterable[str]) -> list[Permission]:
        found = []
        for label in labels:
            try:
                app, codename = label.split(".", 1)
            except ValueError as exc:
                raise ValidationException(f"Invalid permission '{label}'.") from exc
            try:
                found.append(
                    Permission.objects.select_related("content_type").get(
                        content_type__app_label=app, codename=codename
                    )
                )
            except Permission.DoesNotExist as exc:
                raise ValidationException(f"Unknown permission '{label}'.") from exc
        return found

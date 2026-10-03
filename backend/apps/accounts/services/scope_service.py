"""Organization-aware access scopes, decoupled from any organization model.

Phase 2 integration (no change to this module's callers):
    register_scope_type("region", "Region", descendants=region_descendants, validator=region_exists)
where ``descendants(scope_ref)`` yields ``(type, ref)`` pairs below a unit and ``validator(ref)``
checks the referenced object exists.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.common.exceptions import NotFoundException, PermissionDeniedException, ValidationException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional

from ..models import AccountEvent, User, UserScope
from .security_events import record_account_event

GLOBAL = "global"


@dataclass(frozen=True)
class ScopeType:
    name: str
    label: str
    descendants: Callable[[str], Iterable[tuple[str, str]]] | None = None
    validator: Callable[[str], bool] | None = None


_REGISTRY: dict[str, ScopeType] = {}


def register_scope_type(
    name: str,
    label: str,
    *,
    descendants: Callable[[str], Iterable[tuple[str, str]]] | None = None,
    validator: Callable[[str], bool] | None = None,
) -> None:
    """Register (or replace) a scope type. Called by the Organization domain in Phase 2."""
    _REGISTRY[name] = ScopeType(name, label, descendants, validator)


def registered_scope_types() -> dict[str, ScopeType]:
    return dict(_REGISTRY)


register_scope_type(GLOBAL, "Entire organization")
for _name, _label in [
    ("company", "Company"),
    ("corporate_location", "Corporate location"),
    ("department", "Department"),
    ("region", "Region"),
    ("area", "Area"),
    ("restaurant", "Restaurant"),
]:
    register_scope_type(_name, _label)


class ScopeService:
    # --- reads -------------------------------------------------------------------
    @staticmethod
    def get_user_scopes(user: User) -> list[UserScope]:
        now = timezone.now()
        return list(
            UserScope.objects.filter(user=user).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )
        )

    @classmethod
    def has_global_scope(cls, user: Any) -> bool:
        if not getattr(user, "is_authenticated", False):
            return False
        if user.is_superuser:
            return True
        return any(s.scope_type == GLOBAL for s in cls.get_user_scopes(user))

    @classmethod
    def has_scope(cls, user: User, scope_type: str, scope_ref: str) -> bool:
        """Exact grant of (type, ref) - no hierarchy."""
        if user.is_superuser:
            return True
        return any(
            s.scope_type == GLOBAL or (s.scope_type == scope_type and s.scope_ref == str(scope_ref))
            for s in cls.get_user_scopes(user)
        )

    @classmethod
    def can_access_scope(cls, user: Any, scope_type: str, scope_ref: str) -> bool:
        """Exact grant, global grant, or a granted ancestor whose descendants include the target."""
        if not getattr(user, "is_authenticated", False) or not user.is_active:
            return False
        if user.is_superuser:
            return True
        ref = str(scope_ref)
        for s in cls.get_user_scopes(user):
            if s.scope_type == GLOBAL or (s.scope_type == scope_type and s.scope_ref == ref):
                return True
            expander = _REGISTRY.get(s.scope_type)
            if (
                s.include_descendants
                and expander
                and expander.descendants
                and (scope_type, ref) in set(expander.descendants(s.scope_ref))
            ):
                return True
        return False

    @classmethod
    def accessible_refs(cls, user: Any) -> dict[str, set[str]]:
        """{scope_type: {refs}} including descendants. Empty for users without scopes."""
        refs: dict[str, set[str]] = {}
        for s in cls.get_user_scopes(user):
            refs.setdefault(s.scope_type, set()).add(s.scope_ref)
            spec = _REGISTRY.get(s.scope_type)
            if s.include_descendants and spec and spec.descendants:
                for t, r in spec.descendants(s.scope_ref):
                    refs.setdefault(t, set()).add(r)
        return refs

    @classmethod
    def filter_queryset_by_scope(
        cls, user: Any, queryset: QuerySet, lookups: dict[str, str]
    ) -> QuerySet:
        """Restrict ``queryset`` to the user's scopes. Fails closed (``none()``).

        ``lookups`` maps scope type -> ORM path, e.g. ``{"region": "restaurant__area__region_id",
        "restaurant": "restaurant_id"}``. Owned by the *domain* app, so nothing is hard-coded here.
        """
        if not getattr(user, "is_authenticated", False) or not user.is_active:
            return queryset.none()
        if cls.has_global_scope(user):
            return queryset
        q = Q()
        for scope_type, refs in cls.accessible_refs(user).items():
            lookup = lookups.get(scope_type)
            if lookup and refs:
                q |= Q(**{f"{lookup}__in": refs})
        return queryset.filter(q) if q else queryset.none()

    # --- writes ------------------------------------------------------------------
    @staticmethod
    def _validate(scope_type: str, scope_ref: str) -> None:
        spec = _REGISTRY.get(scope_type)
        if spec is None:
            raise ValidationException(f"Unknown scope type '{scope_type}'.")
        if scope_type == GLOBAL:
            if scope_ref != UserScope.GLOBAL_REF:
                raise ValidationException("The global scope reference must be '*'.")
            return
        if not scope_ref or scope_ref == UserScope.GLOBAL_REF or len(scope_ref) > 64:
            raise ValidationException("A valid scope reference is required.")
        if spec.validator and not spec.validator(scope_ref):
            raise ValidationException("The referenced organization unit does not exist.")

    @classmethod
    @transactional
    def grant_scope(
        cls,
        *,
        actor: User,
        user: User,
        scope_type: str,
        scope_ref: str,
        include_descendants: bool = True,
        expires_at: datetime | None = None,
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> UserScope:
        scope_ref = UserScope.GLOBAL_REF if scope_type == GLOBAL else str(scope_ref).strip()
        cls._validate(scope_type, scope_ref)
        if actor.pk == user.pk:
            raise PermissionDeniedException("You cannot change your own access scopes.")
        if not cls.can_access_scope(actor, scope_type, scope_ref):
            raise PermissionDeniedException("You cannot grant a scope outside your own access.")
        scope, created = UserScope.objects.update_or_create(
            user=user,
            scope_type=scope_type,
            scope_ref=scope_ref,
            defaults={
                "include_descendants": include_descendants,
                "expires_at": expires_at,
                "granted_by": actor,
                "granted_at": timezone.now(),
            },
        )
        record_account_event(
            AccountEvent.EventType.SCOPE_GRANTED,
            target=user,
            actor=actor,
            after={
                "scope_type": scope_type,
                "scope_ref": scope_ref,
                "descendants": include_descendants,
            },
            ctx=ctx,
        )
        return scope

    @classmethod
    @transactional
    def revoke_scope(
        cls, *, actor: User, user: User, scope_id: Any, ctx: RequestContext = SYSTEM_CONTEXT
    ) -> None:
        if actor.pk == user.pk:
            raise PermissionDeniedException("You cannot change your own access scopes.")
        scope = UserScope.objects.filter(
            pk=scope_id, user=user
        ).first()  # owner-bound lookup (IDOR)
        if scope is None:
            raise NotFoundException("Scope not found.")
        if not cls.can_access_scope(actor, scope.scope_type, scope.scope_ref):
            raise PermissionDeniedException("You cannot revoke a scope outside your own access.")
        before = {"scope_type": scope.scope_type, "scope_ref": scope.scope_ref}
        scope.delete()
        record_account_event(
            AccountEvent.EventType.SCOPE_REVOKED, target=user, actor=actor, before=before, ctx=ctx
        )

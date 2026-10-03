"""Organization-aware access scopes, decoupled from any organization model (ADR-016).

A scope is ``(scope_type, scope_ref)``. ``accounts`` never imports the Organization domain: the
Organization app *registers* each scope type with optional callbacks in its ``AppConfig.ready()``:

    register_scope_type(
        "region", "Region",
        descendants=lambda ref: [("area", "..."), ("restaurant", "...")],  # units below
        ancestors=lambda ref: [("division", "..."), ("company", "...")],   # units above
        validator=lambda ref: True,        # does the unit exist?
        normalizer=lambda ref: "<uuid>",   # accept a code or UUID, return the canonical ref
        describe=lambda ref: "REG-001 Lahore Region",  # human label
    )

All callbacks are optional, so plain types (``global`` or test types) keep working.
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
RefList = Iterable[tuple[str, str]]


@dataclass(frozen=True)
class ScopeType:
    name: str
    label: str
    descendants: Callable[[str], RefList] | None = None
    validator: Callable[[str], bool] | None = None
    ancestors: Callable[[str], RefList] | None = None
    normalizer: Callable[[str], str | None] | None = None
    describe: Callable[[str], str] | None = None


_REGISTRY: dict[str, ScopeType] = {}


def register_scope_type(
    name: str,
    label: str,
    *,
    descendants: Callable[[str], RefList] | None = None,
    validator: Callable[[str], bool] | None = None,
    ancestors: Callable[[str], RefList] | None = None,
    normalizer: Callable[[str], str | None] | None = None,
    describe: Callable[[str], str] | None = None,
) -> None:
    """Register (or replace) a scope type."""
    _REGISTRY[name] = ScopeType(
        name, label, descendants, validator, ancestors, normalizer, describe
    )


def restore_scope_type(spec: ScopeType) -> None:
    """Put back a previously captured registration (used by tests that swap callbacks)."""
    _REGISTRY[spec.name] = spec


def registered_scope_types() -> dict[str, ScopeType]:
    return dict(_REGISTRY)


register_scope_type(GLOBAL, "Entire organization")
for _name, _label in [
    ("company", "Company"),
    ("division", "Division"),
    ("corporate_location", "Corporate location"),
    ("department", "Department"),
    ("region", "Region"),
    ("area", "Area"),
    ("restaurant", "Restaurant"),
]:
    register_scope_type(_name, _label)


def _active(user: Any) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_active", False))


class ScopeService:
    # --------------------------------------------------------------- reads
    @staticmethod
    def get_user_scopes(user: User) -> list[UserScope]:
        """Active scopes, memoised on the user *instance* (one request; cleared on grant/revoke)."""
        cached = getattr(user, "_ems_scope_cache", None)
        if cached is not None:
            return cached
        now = timezone.now()
        scopes = list(
            UserScope.objects.filter(user=user).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )
        )
        if getattr(user, "pk", None):
            user._ems_scope_cache = scopes  # type: ignore[union-attr,attr-defined]
        return scopes

    @staticmethod
    def clear_cache(user: Any) -> None:
        if user is not None:
            user.__dict__.pop("_ems_scope_cache", None)

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

    # ---- hierarchy helpers (delegate to the registered callbacks) ----
    @staticmethod
    def get_descendants(scope_type: str, scope_ref: str) -> list[tuple[str, str]]:
        spec = _REGISTRY.get(scope_type)
        return list(spec.descendants(str(scope_ref))) if spec and spec.descendants else []

    @staticmethod
    def get_ancestors(scope_type: str, scope_ref: str) -> list[tuple[str, str]]:
        spec = _REGISTRY.get(scope_type)
        return list(spec.ancestors(str(scope_ref))) if spec and spec.ancestors else []

    @staticmethod
    def describe(scope_type: str, scope_ref: str) -> str:
        if scope_type == GLOBAL:
            return "Entire organization"
        spec = _REGISTRY.get(scope_type)
        if spec and spec.describe:
            try:
                return spec.describe(scope_ref) or scope_ref
            except Exception:  # describing must never break a page
                return scope_ref
        return scope_ref

    @classmethod
    def can_access_scope(cls, user: Any, scope_type: str, scope_ref: str) -> bool:
        """Exact grant, global grant, or a granted ancestor (with descendants) of the target.

        Uses the target's *ancestors* (one lookup) when registered; falls back to expanding the
        user's scopes via *descendants* for types without an ancestors callback.
        """
        if not _active(user):
            return False
        if user.is_superuser:
            return True
        ref = str(scope_ref)
        scopes = cls.get_user_scopes(user)
        if not scopes:
            return False
        ancestors = set(cls.get_ancestors(scope_type, ref))
        for s in scopes:
            if s.scope_type == GLOBAL or (s.scope_type == scope_type and s.scope_ref == ref):
                return True
            if s.include_descendants and (s.scope_type, s.scope_ref) in ancestors:
                return True
        target_spec = _REGISTRY.get(scope_type)
        if target_spec and target_spec.ancestors:
            return False  # ancestors are authoritative when the target type provides them
        for s in scopes:
            spec = _REGISTRY.get(s.scope_type)
            if (
                s.include_descendants
                and spec
                and spec.descendants
                and (scope_type, ref) in set(spec.descendants(s.scope_ref))
            ):
                return True
        return False

    # Phase 2 name for the same check (organization vocabulary).
    user_can_access_organization = can_access_scope

    @classmethod
    def resolve_user_organization_scopes(cls, user: User) -> list[dict[str, Any]]:
        """The user's active scopes with human-readable labels (for UI / API)."""
        rows = []
        for s in sorted(cls.get_user_scopes(user), key=lambda x: (x.scope_type, x.scope_ref)):
            spec = _REGISTRY.get(s.scope_type)
            rows.append(
                {
                    "id": s.pk,
                    "type": s.scope_type,
                    "type_label": spec.label if spec else s.scope_type,
                    "ref": s.scope_ref,
                    "display": cls.describe(s.scope_type, s.scope_ref),
                    "include_descendants": s.include_descendants,
                    "granted_at": s.granted_at,
                    "expires_at": s.expires_at,
                }
            )
        return rows

    @classmethod
    def accessible_refs(cls, user: Any) -> dict[str, set[str]]:
        """{scope_type: {refs}} including descendants. Empty for users without scopes."""
        refs: dict[str, set[str]] = {}
        for s in cls.get_user_scopes(user):
            refs.setdefault(s.scope_type, set()).add(s.scope_ref)
            if s.include_descendants:
                for t, r in cls.get_descendants(s.scope_type, s.scope_ref):
                    refs.setdefault(t, set()).add(r)
        return refs

    @classmethod
    def filter_queryset_by_scope(
        cls,
        user: Any,
        queryset: QuerySet,
        lookups: dict[str, str],
        own_type: str | None = None,
    ) -> QuerySet:
        """Restrict ``queryset`` to the user's scopes. Fails closed (``none()``).

        ``lookups`` maps scope type -> ORM path to that unit's id. A domain app passes *hierarchical*
        lookups (e.g. for restaurants ``{"restaurant": "id", "area": "area_id",
        "region": "area__region_id", ...}``) so inheritance is resolved by SQL joins without expanding
        descendants. Scope types missing from ``lookups`` fall back to descendant expansion.
        ``own_type`` is the type of the queryset's rows: a scope *without* ``include_descendants``
        only matches rows of its own type.
        """
        if not _active(user):
            return queryset.none()
        if cls.has_global_scope(user):
            return queryset
        direct: dict[str, set[str]] = {}
        for s in cls.get_user_scopes(user):
            covers_children = s.include_descendants or own_type is None or s.scope_type == own_type
            if s.scope_type in lookups and covers_children:
                direct.setdefault(s.scope_type, set()).add(s.scope_ref)
            elif s.include_descendants:
                for t, r in cls.get_descendants(s.scope_type, s.scope_ref):
                    if t in lookups:
                        direct.setdefault(t, set()).add(r)
        q = Q()
        for scope_type, refs in direct.items():
            q |= Q(**{f"{lookups[scope_type]}__in": refs})
        return queryset.filter(q) if q else queryset.none()

    # -------------------------------------------------------------- writes
    @staticmethod
    def _normalize(scope_type: str, scope_ref: str) -> str:
        spec = _REGISTRY.get(scope_type)
        if spec is None:
            raise ValidationException(f"Unknown scope type '{scope_type}'.")
        if scope_type == GLOBAL:
            return UserScope.GLOBAL_REF  # the reference is irrelevant for the global scope
        if not scope_ref or scope_ref == UserScope.GLOBAL_REF or len(scope_ref) > 64:
            raise ValidationException("A valid scope reference is required.")
        if spec.normalizer:
            canonical = spec.normalizer(scope_ref)
            if not canonical:
                raise ValidationException(
                    "The referenced organization unit does not exist.",
                    details={"scope_ref": ["No organization unit with this code or id."]},
                )
            scope_ref = canonical
        if spec.validator and not spec.validator(scope_ref):
            raise ValidationException(
                "The referenced organization unit does not exist.",
                details={"scope_ref": ["No organization unit with this code or id."]},
            )
        return scope_ref

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
        scope_ref = cls._normalize(scope_type, str(scope_ref).strip())
        if actor.pk == user.pk:
            raise PermissionDeniedException("You cannot change your own access scopes.")
        if not cls.can_access_scope(actor, scope_type, scope_ref):
            raise PermissionDeniedException("You cannot grant a scope outside your own access.")
        cls.clear_cache(user)
        scope, _created = UserScope.objects.update_or_create(
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
                "label": cls.describe(scope_type, scope_ref),
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
        scope = UserScope.objects.filter(pk=scope_id, user=user).first()  # owner-bound (IDOR)
        if scope is None:
            raise NotFoundException("Scope not found.")
        if not cls.can_access_scope(actor, scope.scope_type, scope.scope_ref):
            raise PermissionDeniedException("You cannot revoke a scope outside your own access.")
        before = {
            "scope_type": scope.scope_type,
            "scope_ref": scope.scope_ref,
            "label": cls.describe(scope.scope_type, scope.scope_ref),
        }
        scope.delete()
        cls.clear_cache(user)
        record_account_event(
            AccountEvent.EventType.SCOPE_REVOKED, target=user, actor=actor, before=before, ctx=ctx
        )

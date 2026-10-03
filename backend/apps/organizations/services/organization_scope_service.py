"""Connects Phase 1 ``UserScope`` to real organization units (ADR-016).

* ``register_organization_scopes()`` (called from ``OrganizationsConfig.ready``) registers every
  org type with ``ScopeService`` callbacks: descendants, ancestors, existence validator,
  code-or-UUID normaliser and a human label. ``accounts`` never imports this app.
* ``OrganizationScopeService`` gives domains scope-filtered querysets via *hierarchical lookups*
  resolved by SQL joins (a Region scope covers its Areas and Restaurants without expanding ids).

Scope references are unit UUIDs (stable even if names change); administrators may type the
business code (e.g. ``RST-LHR-001``) and it is normalised to the UUID.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db.models import Model, QuerySet

from apps.accounts.services import ScopeService, register_scope_type

from ..hierarchy import ORG_TYPES, ancestor_paths, descendant_paths, org_type_of, scope_lookups


def _uuid(ref: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(ref))
    except (ValueError, TypeError, AttributeError):
        return None


def _make_callbacks(key: str) -> dict[str, Any]:
    t = ORG_TYPES[key]
    manager = t.model._default_manager

    def normalizer(ref: str) -> str | None:
        pk = _uuid(ref)
        if pk is not None:
            return str(pk) if manager.filter(pk=pk).exists() else None
        found = manager.filter(code__iexact=str(ref).strip()).values_list("pk", flat=True).first()
        return str(found) if found else None

    def validator(ref: str) -> bool:
        pk = _uuid(ref)
        return pk is not None and manager.filter(pk=pk).exists()

    def describe(ref: str) -> str:
        pk = _uuid(ref)
        row = manager.filter(pk=pk).values_list("code", "name").first() if pk else None
        return f"{row[0]} · {row[1]}" if row else f"{ref} (unknown)"

    def ancestors(ref: str) -> list[tuple[str, str]]:
        pk = _uuid(ref)
        paths = ancestor_paths(key)
        if pk is None or not paths:
            return []
        values = manager.filter(pk=pk).values_list(*[f"{p}_id" for p in paths.values()]).first()
        if not values:
            return []
        return [(anc, str(v)) for anc, v in zip(paths, values, strict=True) if v]

    def descendants(ref: str) -> list[tuple[str, str]]:
        pk = _uuid(ref)
        if pk is None:
            return []
        out: list[tuple[str, str]] = []
        for child_key, path in descendant_paths(key).items():
            ids = (
                ORG_TYPES[child_key]
                .model._default_manager.filter(**{f"{path}_id": pk})
                .values_list("pk", flat=True)
            )
            out.extend((child_key, str(i)) for i in ids)
        return out

    return {
        "normalizer": normalizer,
        "validator": validator,
        "describe": describe,
        "ancestors": ancestors,
        "descendants": descendants,
    }


def register_organization_scopes() -> None:
    for key, t in ORG_TYPES.items():
        register_scope_type(key, t.label, **_make_callbacks(key))


class OrganizationScopeService:
    """Scope-aware access to organization data. Fail closed: no scope -> nothing."""

    @staticmethod
    def filter_queryset(user: Any, queryset: QuerySet, key: str, prefix: str = "") -> QuerySet:
        """Restrict any queryset that points (via ``prefix``) to an org unit of type ``key``.

        Organization lists: ``filter_queryset(user, Restaurant.objects.all(), "restaurant")``.
        Future domains:     ``filter_queryset(user, Assignment.objects.all(), "restaurant", "restaurant")``.
        """
        own_type = key if not prefix else None
        return ScopeService.filter_queryset_by_scope(
            user, queryset, scope_lookups(key, prefix), own_type
        )

    @classmethod
    def visible(cls, user: Any, key: str) -> QuerySet:
        return cls.filter_queryset(user, ORG_TYPES[key].model._default_manager.all(), key)

    @staticmethod
    def can_access(user: Any, obj: Model) -> bool:
        return ScopeService.user_can_access_organization(user, org_type_of(obj).key, str(obj.pk))

    @staticmethod
    def resolve_user_organization_scopes(user: Any) -> list[dict[str, Any]]:
        return ScopeService.resolve_user_organization_scopes(user)

    @staticmethod
    def get_descendants(obj: Model) -> list[tuple[str, str]]:
        return ScopeService.get_descendants(org_type_of(obj).key, str(obj.pk))

    @staticmethod
    def get_ancestors(obj: Model) -> list[tuple[str, str]]:
        return ScopeService.get_ancestors(org_type_of(obj).key, str(obj.pk))


__all__ = ["OrganizationScopeService", "register_organization_scopes", "scope_lookups"]

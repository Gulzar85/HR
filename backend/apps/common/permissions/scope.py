"""Organization-scope permission infrastructure (no rules implemented in Phase 0).

Permission pipeline:  Role -> Permission -> Organization Scope -> Object-level permission
(guardian). A *scope resolver* narrows a queryset to what a user may see (all / region /
area / restaurant / department / self). Domain apps register one resolver per model in
their ``apps.py`` ``ready()``; views and selectors call ``apply_scope`` and never hard-code
role rules. Phases 1-3 supply the actual resolvers.
"""

from __future__ import annotations

from typing import Any, Protocol

from django.db.models import QuerySet


class ScopeResolver(Protocol):
    def __call__(self, user: Any, queryset: QuerySet) -> QuerySet: ...


_RESOLVERS: dict[str, ScopeResolver] = {}


def register_scope_resolver(model_label: str, resolver: ScopeResolver) -> None:
    """model_label: ``app_label.ModelName`` (lower-case model name)."""
    _RESOLVERS[model_label.lower()] = resolver


def apply_scope(user: Any, queryset: QuerySet) -> QuerySet:
    """Narrow ``queryset`` to the user's scope. Fails closed if no resolver is registered."""
    if getattr(user, "is_superuser", False):
        return queryset
    resolver = _RESOLVERS.get(queryset.model._meta.label_lower)
    if resolver is None:
        return queryset.none()
    return resolver(user, queryset)

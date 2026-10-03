"""Read-side organization queries: scoped lists, the dynamic tree, history and as-of-date lookups.

Tree cost is constant: one query per organization level (7) plus, for scoped users, one id query per
level - regardless of how many restaurants exist. No caching is used (not needed at this scale).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from django.db.models import Count, Q, QuerySet
from django.urls import reverse

from apps.accounts.services import ScopeService

from ..hierarchy import ORG_TYPES, TYPE_ORDER, ancestor_paths, children_types, org_type_of
from ..models import LIVE_STATUSES, OrganizationHistory, OrganizationRelationship
from ..services.organization_scope_service import OrganizationScopeService

_DUMMY = uuid.UUID(int=0)


def visible_units(user: Any, key: str) -> QuerySet:
    """Scope-filtered queryset of one org type with its parent chain joined (no N+1 in lists)."""
    qs = OrganizationScopeService.visible(user, key)
    paths = ancestor_paths(key)
    if paths:
        qs = qs.select_related(max(paths.values(), key=len))
    return qs.order_by("code")


def get_unit_for_user(user: Any, key: str, pk: Any):
    """Object lookup *through* the user's scope: out-of-scope ids behave exactly like missing ids
    (404), so knowing a UUID grants nothing (IDOR protection)."""
    from django.shortcuts import get_object_or_404

    return get_object_or_404(visible_units(user, key), pk=pk)


def children_of(user: Any, obj: Any) -> list[tuple[Any, QuerySet]]:
    """[(child OrgType, scoped queryset of direct children)] for a detail page."""
    out = []
    for ct in children_types(org_type_of(obj).key):
        qs = visible_units(user, ct.key).filter(**{str(ct.parent_field): obj})
        out.append((ct, qs))
    return out


def history_for(obj: Any, limit: int = 50) -> QuerySet[OrganizationHistory]:
    return OrganizationHistory.objects.filter(
        entity_type=org_type_of(obj).key, entity_id=obj.pk
    ).select_related("actor")[:limit]


def relationships_for(obj: Any) -> list[OrganizationRelationship]:
    """Parent history (newest first) with each row's ``parent`` unit attached (one query per type)."""
    rows = list(
        OrganizationRelationship.objects.filter(
            child_type=org_type_of(obj).key, child_id=obj.pk
        ).order_by("-effective_from")
    )
    by_type: dict[str, set] = {}
    for r in rows:
        by_type.setdefault(r.parent_type, set()).add(r.parent_id)
    units = {
        (key, u.pk): u
        for key, ids in by_type.items()
        for u in ORG_TYPES[key].model._default_manager.filter(pk__in=ids).only("id", "code", "name")
    }
    for r in rows:
        r.parent = units.get((r.parent_type, r.parent_id))  # type: ignore[attr-defined]
    return rows


# --------------------------------------------------------------- as-of-date (historical) queries
def parent_on(child_type: str, child_id: Any, on: date) -> tuple[str, Any] | None:
    """(parent_type, parent_id) effective on ``on`` (half-open intervals), or None."""
    rel = (
        OrganizationRelationship.objects.filter(
            child_type=child_type, child_id=child_id, effective_from__lte=on
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=on))
        .order_by("-effective_from")
        .first()
    )
    return (rel.parent_type, rel.parent_id) if rel else None


def ancestors_on(obj: Any, on: date) -> list[Any]:
    """Ancestor chain (nearest first) as it was on ``on``. E.g. which Region did Restaurant X
    belong to in 2025: ``[u for u in ancestors_on(restaurant, date(2025, 6, 30)) if u.ORG_TYPE == "region"]``."""
    chain = []
    key, pk = org_type_of(obj).key, obj.pk
    while True:
        found = parent_on(key, pk, on)
        if not found:
            break
        key, pk = found
        unit = ORG_TYPES[key].model._default_manager.filter(pk=pk).first()
        if unit is None:
            break
        chain.append(unit)
    return chain


def ancestor_of_type_on(obj: Any, key: str, on: date):
    return next((u for u in ancestors_on(obj, on) if key == u.ORG_TYPE), None)


# ------------------------------------------------------------------------------- dashboard
def counts_for(user: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key in TYPE_ORDER:
        data[key] = OrganizationScopeService.visible(user, key).count()
    restaurants = OrganizationScopeService.visible(user, "restaurant")
    by_status = dict(restaurants.values_list("status").annotate(n=Count("pk")).order_by())
    data["restaurants_by_status"] = by_status
    data["restaurants_active"] = by_status.get("active", 0)
    data["restaurants_inactive"] = sum(v for k, v in by_status.items() if k != "active")
    return data


# ------------------------------------------------------------------------------------ tree
TREE_FIELDS = ("id", "code", "name", "status")


def _url_templates() -> dict[str, str]:
    return {
        key: reverse(f"organizations:{key}_detail", args=[_DUMMY]).replace(str(_DUMMY), "{id}")
        for key in ORG_TYPES
    }


def get_organization_tree(
    user: Any = None, *, include_inactive: bool = True
) -> list[dict[str, Any]]:
    """Nested dicts built from the database:
    ``{"type", "id", "code", "name", "status", "url", "context", "children": [...], "counts": {...}}``.

    For a scoped user only units in scope are returned, plus their ancestors flagged
    ``context=True`` (shown for orientation, not navigable).
    """
    urls = _url_templates()
    nodes: dict[tuple[str, str], dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for key in TYPE_ORDER:
        t = ORG_TYPES[key]
        fields = list(TREE_FIELDS) + ([f"{t.parent_field}_id"] if t.parent_field else [])
        qs = t.model._default_manager.order_by("code").values(*fields)
        if not include_inactive:
            qs = qs.filter(status__in=LIVE_STATUSES)
        for row in qs:
            node = {
                "type": key,
                "type_label": t.label,
                "icon": t.icon,
                "id": str(row["id"]),
                "code": row["code"],
                "name": row["name"],
                "status": row["status"],
                "url": urls[key].format(id=row["id"]),
                "context": False,
                "children": [],
            }
            nodes[(key, node["id"])] = node
            if t.parent_field:
                parent = nodes.get((str(t.parent_key), str(row[f"{t.parent_field}_id"])))
                if parent is not None:
                    parent["children"].append(node)
            else:
                roots.append(node)

    if user is not None and not ScopeService.has_global_scope(user):
        allowed = {
            (key, str(pk))
            for key in TYPE_ORDER
            for pk in OrganizationScopeService.visible(user, key).values_list("pk", flat=True)
        }
        roots = _prune(roots, allowed)

    for root in roots:
        _count(root)
    return roots


def _prune(nodes: list[dict[str, Any]], allowed: set[tuple[str, str]]) -> list[dict[str, Any]]:
    kept = []
    for node in nodes:
        node["children"] = _prune(node["children"], allowed)
        if (node["type"], node["id"]) in allowed:
            kept.append(node)
        elif node["children"]:
            node["context"] = True
            kept.append(node)
    return kept


def _count(node: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for child in node["children"]:
        counts[child["type"]] = counts.get(child["type"], 0) + 1
        for k, v in _count(child).items():
            counts[k] = counts.get(k, 0) + v
    node["counts"] = counts
    return counts


def flatten_tree(roots: list[dict[str, Any]], depth: int = 0):
    for node in roots:
        yield depth, node
        yield from flatten_tree(node["children"], depth + 1)

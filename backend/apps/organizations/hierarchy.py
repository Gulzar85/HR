"""The locked organization hierarchy, declared once (ADR-013, ADR-017).

    Company
    ├── Division[CORPORATE] ── CorporateLocation ── Department
    └── Division[OPERATIONS] ── Region ── Area ── Restaurant

Services, selectors, scope resolution, the tree and the API all derive parent/child rules and
ORM paths from ``ORG_TYPES``; nothing else hard-codes the structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any

from apps.common.exceptions import BusinessRuleException

from .models import (
    Area,
    Company,
    CorporateLocation,
    Department,
    Division,
    Region,
    Restaurant,
    StructureType,
)


@dataclass(frozen=True)
class OrgType:
    key: str
    label: str
    plural: str
    model: type[Any]  # an OrganizationUnit subclass
    slug: str  # URL segment
    icon: str
    parent_key: str | None = None
    parent_field: str | None = None
    parent_structure: str | None = None  # required Division.structure_type of the parent

    @property
    def permission_codename(self) -> str:
        return self.model._meta.model_name  # type: ignore[union-attr,return-value]

    def perm(self, action: str) -> str:
        return f"organizations.{action}_{self.permission_codename}"


ORG_TYPES: dict[str, OrgType] = {
    t.key: t
    for t in [
        OrgType("company", "Company", "Companies", Company, "companies", "building-2"),
        OrgType("division", "Division", "Divisions", Division, "divisions", "git-fork", "company", "company"),
        OrgType(
            "corporate_location", "Corporate location", "Corporate locations", CorporateLocation,
            "corporate-locations", "landmark", "division", "division", StructureType.CORPORATE,
        ),
        OrgType("department", "Department", "Departments", Department, "departments", "briefcase", "corporate_location", "location"),
        OrgType(
            "region", "Region", "Regions", Region, "regions", "map", "division", "division",
            StructureType.OPERATIONS,
        ),
        OrgType("area", "Area", "Areas", Area, "areas", "map-pinned", "region", "region"),
        OrgType("restaurant", "Restaurant", "Restaurants", Restaurant, "restaurants", "store", "area", "area"),
    ]
}  # fmt: skip

TYPE_ORDER = list(ORG_TYPES)
BY_MODEL: dict[type[Any], OrgType] = {t.model: t for t in ORG_TYPES.values()}


def org_type_of(obj: Any) -> OrgType:
    return BY_MODEL[type(obj)]


def children_types(key: str) -> list[OrgType]:
    return [t for t in ORG_TYPES.values() if t.parent_key == key]


@cache
def ancestor_paths(key: str) -> dict[str, str]:
    """{ancestor_type: ORM path from `key` to that ancestor}, e.g. restaurant ->
    {"area": "area", "region": "area__region", "division": "area__region__division", ...}."""
    paths: dict[str, str] = {}
    t = ORG_TYPES[key]
    path = ""
    while t.parent_key:
        path = f"{path}__{t.parent_field}" if path else t.parent_field  # type: ignore[assignment]
        paths[t.parent_key] = path
        t = ORG_TYPES[t.parent_key]
    return paths


@cache
def descendant_paths(key: str) -> dict[str, str]:
    """{descendant_type: ORM path from that descendant up to `key`} (inverse of ancestor_paths)."""
    return {k: ancestor_paths(k)[key] for k in ORG_TYPES if key in ancestor_paths(k)}


def scope_lookups(key: str, prefix: str = "") -> dict[str, str]:
    """Hierarchical lookups for ``ScopeService.filter_queryset_by_scope``.

    ``key`` is the org type the queryset points to; ``prefix`` is the FK path to it (empty when the
    queryset *is* that org type). Example for a future Assignment queryset:
    ``scope_lookups("restaurant", "restaurant")`` ->
    ``{"restaurant": "restaurant_id", "area": "restaurant__area_id", ..., "company": ...}``.
    """
    own = f"{prefix}_id" if prefix else "id"
    lookups = {key: own}
    for ancestor, path in ancestor_paths(key).items():
        lookups[ancestor] = f"{prefix}__{path}_id" if prefix else f"{path}_id"
    return lookups


def get_parent(obj: Any) -> Any | None:
    t = org_type_of(obj)
    return getattr(obj, t.parent_field) if t.parent_field else None


def validate_parent(key: str, parent: Any | None) -> None:
    """Enforce the locked hierarchy: right parent type and, for divisions, right structure."""
    t = ORG_TYPES[key]
    if t.parent_key is None:
        if parent is not None:
            raise BusinessRuleException(f"A {t.label.lower()} has no parent.")
        return
    if parent is None:
        raise BusinessRuleException(
            f"A {t.label.lower()} must belong to a {ORG_TYPES[t.parent_key].label.lower()}.",
            code="invalid_hierarchy",
        )
    if not isinstance(parent, ORG_TYPES[t.parent_key].model):
        raise BusinessRuleException(
            f"A {t.label.lower()} must belong to a {ORG_TYPES[t.parent_key].label.lower()}, "
            f"not a {org_type_of(parent).label.lower()}.",
            code="invalid_hierarchy",
        )
    if t.parent_structure and getattr(parent, "structure_type", None) != t.parent_structure:
        raise BusinessRuleException(
            f"A {t.label.lower()} must belong to a {StructureType(t.parent_structure).label.split(' (')[0]} "
            f"division.",
            code="invalid_hierarchy",
        )


def ancestors_of(obj: Any) -> list[Any]:
    """Ordered list of ancestors, nearest first (single query via select_related)."""
    t = org_type_of(obj)
    paths = ancestor_paths(t.key)
    if not paths:
        return []
    deepest = max(paths.values(), key=len)
    fresh = t.model._default_manager.select_related(deepest).get(pk=obj.pk)
    result, node = [], fresh
    while True:
        parent = get_parent(node)
        if parent is None:
            break
        result.append(parent)
        node = parent
    return result


def company_of(obj: Any) -> Company:
    return obj if isinstance(obj, Company) else ancestors_of(obj)[-1]


def assert_not_own_ancestor(obj: Any, new_parent: Any) -> None:
    """Circular-hierarchy guard. Typed FKs already make cycles impossible today; this keeps the
    rule explicit should a self-referencing level ever be introduced."""
    if new_parent is None:
        return
    chain = [new_parent, *ancestors_of(new_parent)]
    if any(type(n) is type(obj) and n.pk == obj.pk for n in chain):
        raise BusinessRuleException(
            "An organization unit cannot become its own ancestor.", code="circular_hierarchy"
        )

"""Organization data-quality checks (registered into apps.data_quality).

The database already enforces most rules (NOT NULL parents, PROTECT, unique codes, date checks);
these checks catch what constraints cannot express, and protect against data loaded around the
service layer (imports, manual SQL, restores).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from django.db.models import F, Q
from django.db.models.functions import Upper

from apps.data_quality.registry import ERROR, WARNING, Issue, register_check

from .hierarchy import ORG_TYPES, TYPE_ORDER
from .models import LIVE_STATUSES, OrganizationRelationship


def _issue(code, severity, msg, key, obj, **details) -> Issue:
    return Issue(code, severity, msg, key, str(obj.pk), obj.code, details)


@register_check(
    "organizations", "ORG-NO-RELATIONSHIP", "Unit without a current parent relationship record"
)
def missing_parent_relationship() -> Iterable[Issue]:
    for key in TYPE_ORDER:
        t = ORG_TYPES[key]
        if not t.parent_key:
            continue
        current = OrganizationRelationship.objects.filter(child_type=key, effective_to__isnull=True)
        current_ids = set(current.values_list("child_id", flat=True))
        for obj in t.model._default_manager.only("id", "code"):
            if obj.pk not in current_ids:
                yield _issue(
                    "ORG-NO-RELATIONSHIP",
                    ERROR,
                    f"{obj.code} has no current parent relationship.",
                    key,
                    obj,
                )


@register_check(
    "organizations",
    "ORG-RELATIONSHIP-MISMATCH",
    "Current relationship disagrees with the parent FK",
)
def relationship_mismatch() -> Iterable[Issue]:
    for key in TYPE_ORDER:
        t = ORG_TYPES[key]
        if not t.parent_key:
            continue
        rel = {
            r.child_id: r.parent_id
            for r in OrganizationRelationship.objects.filter(
                child_type=key, effective_to__isnull=True
            )
        }
        for obj in t.model._default_manager.only("id", "code", f"{t.parent_field}_id"):
            parent_id = getattr(obj, f"{t.parent_field}_id")
            if obj.pk in rel and rel[obj.pk] != parent_id:
                yield _issue(
                    "ORG-RELATIONSHIP-MISMATCH",
                    ERROR,
                    f"{obj.code}: parent FK and current relationship differ.",
                    key,
                    obj,
                )


@register_check(
    "organizations", "ORG-INACTIVE-PARENT", "Live unit under a parent that is no longer live"
)
def inactive_parent_with_live_child() -> Iterable[Issue]:
    for key in TYPE_ORDER:
        t = ORG_TYPES[key]
        if not t.parent_field:
            continue
        qs = (
            t.model._default_manager.filter(status__in=LIVE_STATUSES)
            .exclude(**{f"{t.parent_field}__status__in": LIVE_STATUSES})
            .select_related(t.parent_field)
        )
        for obj in qs:
            parent = getattr(obj, t.parent_field)
            yield _issue(
                "ORG-INACTIVE-PARENT",
                ERROR,
                f"{obj.code} is {obj.status} but its parent {parent.code} is {parent.status}.",
                key,
                obj,
            )


@register_check(
    "organizations",
    "ORG-INVALID-HIERARCHY",
    "Parent division has the wrong structure type, or child dates precede parent",
)
def invalid_hierarchy() -> Iterable[Issue]:
    for key in TYPE_ORDER:
        t = ORG_TYPES[key]
        if t.parent_structure:
            for obj in t.model._default_manager.exclude(
                **{f"{t.parent_field}__structure_type": t.parent_structure}
            ):
                yield _issue(
                    "ORG-INVALID-HIERARCHY",
                    ERROR,
                    f"{obj.code} sits under a division that is not '{t.parent_structure}'.",
                    key,
                    obj,
                )
        if t.parent_field:
            early = t.model._default_manager.filter(
                effective_from__lt=F(f"{t.parent_field}__effective_from")
            )
            for obj in early:
                yield _issue(
                    "ORG-INVALID-HIERARCHY",
                    WARNING,
                    f"{obj.code} starts before its parent.",
                    key,
                    obj,
                )


@register_check(
    "organizations", "ORG-DUPLICATE-CODE", "Codes that differ only by case or whitespace"
)
def duplicate_codes() -> Iterable[Issue]:
    for key in TYPE_ORDER:
        t = ORG_TYPES[key]
        seen: dict[str, list] = defaultdict(list)
        for obj in t.model._default_manager.annotate(norm=Upper("code")).only("id", "code"):
            seen[obj.norm.strip()].append(obj)
        for objs in seen.values():
            if len(objs) > 1:
                for obj in objs:
                    yield _issue(
                        "ORG-DUPLICATE-CODE",
                        ERROR,
                        f"Duplicate business code {obj.code}.",
                        key,
                        obj,
                    )


@register_check("organizations", "ORG-INVALID-DATES", "Effective dates inconsistent with status")
def invalid_dates() -> Iterable[Issue]:
    for key in TYPE_ORDER:
        t = ORG_TYPES[key]
        bad = t.model._default_manager.filter(
            Q(effective_to__lt=F("effective_from"))
            | Q(status__in=LIVE_STATUSES, effective_to__isnull=False)
        )
        for obj in bad:
            yield _issue(
                "ORG-INVALID-DATES",
                WARNING,
                f"{obj.code} has effective dates that do not match its status.",
                key,
                obj,
            )


@register_check(
    "organizations",
    "ORG-OVERLAPPING-RELATIONSHIPS",
    "Overlapping parent relationships for one unit",
)
def overlapping_relationships() -> Iterable[Issue]:
    rows = OrganizationRelationship.objects.order_by("child_type", "child_id", "effective_from")
    prev = None
    for rel in rows:
        if prev and (prev.child_type, prev.child_id) == (rel.child_type, rel.child_id):
            prev_end = prev.effective_to
            if prev_end is None or prev_end > rel.effective_from:
                yield Issue(
                    "ORG-OVERLAPPING-RELATIONSHIPS", ERROR,
                    f"Overlapping parent relationships for {rel.child_type} {rel.child_id}.",
                    rel.child_type, str(rel.child_id),
                )  # fmt: skip
        prev = rel

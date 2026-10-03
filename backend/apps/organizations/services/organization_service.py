"""Generic organization-unit service and the ``OrganizationService`` facade.

Every mutation of every organization type goes through ``OrgUnitService`` subclasses, so web views,
API views, management commands and future domains share exactly one set of rules:

* permission check (``organizations.add_<model>`` / ``change_`` / ``change_organization_status`` /
  ``move_organization``) **and** organization-scope check (actor must have the parent / unit in scope);
* locked hierarchy (``hierarchy.validate_parent``) and circular-reference guard;
* status state machine with parent/child integrity (no active child under an inactive parent);
* immutable business codes generated via ``apps.common.services.generate_code``;
* effective-dated parent relationships + OrganizationHistory + AuditLog, all in one transaction.

``actor=None`` is a trusted system call (seed commands).
"""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from apps.accounts.services import PermissionService, ScopeService
from apps.common.exceptions import (
    BusinessRuleException,
    ConflictException,
    PermissionDeniedException,
    ValidationException,
)
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional
from apps.common.utils import today_local

from ..hierarchy import (
    ORG_TYPES,
    OrgType,
    assert_not_own_ancestor,
    children_types,
    company_of,
    get_parent,
    org_type_of,
    validate_parent,
)
from ..models import LIVE_STATUSES, OrganizationHistory, OrganizationRelationship, OrgStatus
from .history import diff, record_history, snapshot

E = OrganizationHistory.Event
S = OrgStatus

# action -> (allowed source statuses, target status, history event)
GENERIC_TRANSITIONS: dict[str, tuple[frozenset[str], str, str]] = {
    "activate": (frozenset({S.PLANNED, S.INACTIVE}), S.ACTIVE, E.ACTIVATED),
    "deactivate": (frozenset({S.PLANNED, S.ACTIVE}), S.INACTIVE, E.DEACTIVATED),
    "archive": (frozenset({S.INACTIVE}), S.ARCHIVED, E.ARCHIVED),
}


def _authorize(actor: Any, permission: str) -> None:
    if actor is not None:
        PermissionService.require(actor, permission)


def assert_in_scope(actor: Any, obj: Any) -> None:
    """The actor must have ``obj`` (or one of its ancestors) in an organization scope."""
    if actor is None:
        return
    key = org_type_of(obj).key
    if not ScopeService.user_can_access_organization(actor, key, str(obj.pk)):
        raise PermissionDeniedException("This organization unit is outside your access scope.")


class OrgUnitService:
    type_key: ClassVar[str]
    editable_fields: ClassVar[tuple[str, ...]] = ("name", "description")
    create_only_fields: ClassVar[tuple[str, ...]] = ()
    default_status: ClassVar[str] = S.ACTIVE
    initial_statuses: ClassVar[frozenset[str]] = frozenset({S.ACTIVE, S.PLANNED})
    transitions: ClassVar[dict[str, tuple[frozenset[str], str, str]]] = GENERIC_TRANSITIONS

    # ------------------------------------------------------------------ hooks
    @classmethod
    def org_type(cls) -> OrgType:
        return ORG_TYPES[cls.type_key]

    @classmethod
    def generate_code(cls, fields: dict[str, Any], parent: Any) -> str:  # pragma: no cover
        raise NotImplementedError

    @classmethod
    def extra_checks(cls, obj: Any, parent: Any) -> None:
        """Per-type uniqueness/consistency checks before saving (create and move)."""

    @classmethod
    def on_status_change(cls, obj: Any, action: str, when: date) -> None:
        """Per-type side effects of a status transition (e.g. restaurant opening/closing dates)."""

    # ------------------------------------------------------------- helpers
    @classmethod
    def _clean(cls, obj: Any) -> None:
        try:
            obj.full_clean(exclude=["code"], validate_unique=False, validate_constraints=False)
        except DjangoValidationError as exc:
            raise ValidationException(
                "Please correct the highlighted fields.", details=exc.message_dict
            ) from exc

    @classmethod
    def _assert_unique_name(cls, obj: Any, parent: Any) -> None:
        t = cls.org_type()
        if not t.parent_field:
            return
        siblings = t.model._default_manager.filter(
            **{t.parent_field: parent}, name__iexact=obj.name.strip()
        ).exclude(pk=obj.pk)
        if siblings.exists():
            raise ConflictException(
                f"A {t.label.lower()} with this name already exists under {parent.name}.",
                details={"name": ["Already used under this parent."]},
            )

    @classmethod
    def _save(cls, obj: Any) -> None:
        try:
            with transaction.atomic():
                obj.save()
        except IntegrityError as exc:
            raise ConflictException(
                "This conflicts with an existing organization unit (duplicate name or code)."
            ) from exc

    @staticmethod
    def _open_relationship(obj: Any, parent: Any, when: date, actor: Any, reason: str) -> None:
        OrganizationRelationship.objects.create(
            child_type=org_type_of(obj).key,
            child_id=obj.pk,
            parent_type=org_type_of(parent).key,
            parent_id=parent.pk,
            effective_from=when,
            reason=reason[:255],
            created_by=actor if getattr(actor, "pk", None) else None,
        )

    # ------------------------------------------------------------- create
    @classmethod
    @transactional
    def create(
        cls,
        *,
        actor: Any,
        data: dict[str, Any],
        parent: Any = None,
        status: str | None = None,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Any:
        t = cls.org_type()
        _authorize(actor, t.perm("add"))
        validate_parent(t.key, parent)
        if parent is not None:  # re-read + lock: never trust a caller's (possibly stale) copy
            parent = type(parent)._default_manager.select_for_update().get(pk=parent.pk)
        if parent is None:
            if actor is not None and not ScopeService.has_global_scope(actor):
                raise PermissionDeniedException(
                    "Only users with organization-wide scope can create companies."
                )
        else:
            assert_in_scope(actor, parent)
            if not parent.is_live:
                raise BusinessRuleException(
                    f"Cannot add to {parent.code}: it is {parent.get_status_display().lower()}.",
                    code="inactive_parent",
                )
        status = status or cls.default_status
        if status not in cls.initial_statuses:
            raise ValidationException(f"A new {t.label.lower()} cannot start as '{status}'.")
        if status == S.ACTIVE and parent is not None and parent.status != S.ACTIVE:
            raise BusinessRuleException(
                f"Cannot create an active {t.label.lower()} under {parent.code}, which is not active.",
                code="inactive_parent",
            )
        allowed = cls.editable_fields + cls.create_only_fields + ("effective_from",)
        fields = {k: v for k, v in data.items() if k in allowed and v not in (None,)}
        if "effective_from" in fields and not fields["effective_from"]:
            fields.pop("effective_from")
        obj = t.model(**fields, status=status)
        if parent is not None:
            setattr(obj, t.parent_field, parent)  # type: ignore[arg-type]
        if status == S.ACTIVE:
            cls.on_status_change(obj, "activate", obj.effective_from or today_local())
        cls._clean(obj)
        cls._assert_unique_name(obj, parent)
        cls.extra_checks(obj, parent)
        obj.code = cls.generate_code(fields, parent)
        if t.model._default_manager.filter(code=obj.code).exists():
            raise ConflictException(
                f"The code {obj.code} is already in use.", code="duplicate_code"
            )
        cls._save(obj)
        if parent is not None:
            cls._open_relationship(obj, parent, obj.effective_from, actor, reason or "created")
        record_history(
            obj,
            E.CREATED,
            actor=actor,
            after={"code": obj.code, "status": obj.status, **snapshot(obj, cls.editable_fields)},
            reason=reason,
            effective_date=obj.effective_from,
            ctx=ctx,
        )
        return obj

    # ------------------------------------------------------------- update
    @classmethod
    @transactional
    def update(
        cls,
        obj: Any,
        *,
        actor: Any,
        data: dict[str, Any],
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Any:
        t = cls.org_type()
        _authorize(actor, t.perm("change"))
        assert_in_scope(actor, obj)
        obj = t.model._default_manager.select_for_update().get(pk=obj.pk)
        before = snapshot(obj, cls.editable_fields)
        for field in cls.editable_fields:
            if field in data:
                setattr(obj, field, data[field])
        cls._clean(obj)
        cls._assert_unique_name(obj, get_parent(obj))
        b, a = diff(before, snapshot(obj, cls.editable_fields))
        if not a:
            return obj
        cls._save(obj)
        record_history(
            obj,
            E.RENAMED if set(a) == {"name"} else E.UPDATED,
            actor=actor,
            before=b,
            after=a,
            reason=reason,
            ctx=ctx,
        )
        return obj

    # ------------------------------------------------------------- status
    @classmethod
    def allowed_actions(cls, obj: Any) -> list[str]:
        return [a for a, (src, _t, _e) in cls.transitions.items() if obj.status in src]

    @classmethod
    @transactional
    def change_status(
        cls,
        obj: Any,
        action: str,
        *,
        actor: Any,
        reason: str = "",
        effective_date: date | None = None,
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Any:
        t = cls.org_type()
        if action not in cls.transitions:
            raise ValidationException(f"Unknown action '{action}' for a {t.label.lower()}.")
        _authorize(actor, "organizations.change_organization_status")
        assert_in_scope(actor, obj)
        obj = t.model._default_manager.select_for_update().get(pk=obj.pk)
        sources, target, event = cls.transitions[action]
        if obj.status not in sources:
            raise BusinessRuleException(
                f"Cannot {action.replace('_', ' ')} {obj.code}: it is {obj.get_status_display().lower()}.",
                code="invalid_status_transition",
            )
        when = effective_date or today_local()
        if when < obj.effective_from:
            raise BusinessRuleException(
                "The effective date cannot be before the unit's start date."
            )
        parent = get_parent(obj)
        if target == S.ACTIVE and parent is not None and parent.status != S.ACTIVE:
            raise BusinessRuleException(
                f"Cannot activate {obj.code} while its parent {parent.code} is not active.",
                code="inactive_parent",
            )
        if target not in LIVE_STATUSES:
            for child_type in children_types(t.key):
                live = child_type.model._default_manager.filter(
                    **{str(child_type.parent_field): obj}, status__in=LIVE_STATUSES
                ).count()
                if live:
                    raise BusinessRuleException(
                        f"{obj.code} still has {live} active {child_type.plural.lower()}. "
                        "Deactivate, close or move them first.",
                        code="active_children",
                    )
        before = {"status": obj.status, "effective_to": str(obj.effective_to or "")}
        obj.status = target
        obj.effective_to = None if target in LIVE_STATUSES else when
        cls.on_status_change(obj, action, when)
        cls._save(obj)
        record_history(
            obj,
            event,
            actor=actor,
            before=before,
            after={"status": obj.status, "effective_to": str(obj.effective_to or "")},
            reason=reason,
            effective_date=when,
            ctx=ctx,
        )
        return obj

    # --------------------------------------------------------------- move
    @classmethod
    @transactional
    def move(
        cls,
        obj: Any,
        new_parent: Any,
        *,
        actor: Any,
        reason: str = "",
        effective_date: date | None = None,
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Any:
        t = cls.org_type()
        if t.parent_field is None:
            raise BusinessRuleException(f"A {t.label.lower()} cannot be moved.")
        _authorize(actor, "organizations.move_organization")
        assert_in_scope(actor, obj)
        assert_in_scope(actor, new_parent)
        validate_parent(t.key, new_parent)
        new_parent = type(new_parent)._default_manager.select_for_update().get(pk=new_parent.pk)
        obj = t.model._default_manager.select_for_update().get(pk=obj.pk)
        old_parent = get_parent(obj)
        assert old_parent is not None  # every movable type has a parent
        if old_parent.pk == new_parent.pk:
            raise BusinessRuleException(f"{obj.code} already belongs to {new_parent.code}.")
        assert_not_own_ancestor(obj, new_parent)
        if company_of(new_parent).pk != company_of(old_parent).pk:
            raise BusinessRuleException("Moving units between companies is not supported.")
        if not new_parent.is_live:
            raise BusinessRuleException(
                f"Cannot move into {new_parent.code}: it is {new_parent.get_status_display().lower()}.",
                code="inactive_parent",
            )
        if obj.status == S.ACTIVE and new_parent.status != S.ACTIVE:
            raise BusinessRuleException(
                f"An active unit cannot move under {new_parent.code}, which is not active."
            )
        when = effective_date or today_local()
        current = (
            OrganizationRelationship.objects.select_for_update()
            .filter(child_type=t.key, child_id=obj.pk, effective_to__isnull=True)
            .first()
        )
        if current and when < current.effective_from:
            raise BusinessRuleException(
                f"The move date must be on or after {current.effective_from} (current placement start)."
            )
        setattr(obj, t.parent_field, new_parent)
        cls._assert_unique_name(obj, new_parent)
        cls.extra_checks(obj, new_parent)
        if current:
            current.effective_to = when
            current.save(update_fields=["effective_to"])
        cls._save(obj)
        cls._open_relationship(obj, new_parent, when, actor, reason or "moved")
        record_history(
            obj,
            E.MOVED,
            actor=actor,
            before={"parent": old_parent.code},
            after={"parent": new_parent.code},
            reason=reason,
            effective_date=when,
            ctx=ctx,
        )
        return obj


class OrganizationService:
    """Facade: pick the right per-type service for any organization object or type key."""

    _registry: ClassVar[dict[str, type[OrgUnitService]]] = {}

    @classmethod
    def register(cls, service: type[OrgUnitService]) -> type[OrgUnitService]:
        cls._registry[service.type_key] = service
        return service

    @classmethod
    def for_type(cls, key: str) -> type[OrgUnitService]:
        return cls._registry[key]

    @classmethod
    def for_object(cls, obj: Any) -> type[OrgUnitService]:
        return cls._registry[org_type_of(obj).key]

    @classmethod
    def create(cls, key: str, **kwargs: Any) -> Any:
        return cls.for_type(key).create(**kwargs)

    @classmethod
    def update(cls, obj: Any, **kwargs: Any) -> Any:
        return cls.for_object(obj).update(obj, **kwargs)

    @classmethod
    def change_status(cls, obj: Any, action: str, **kwargs: Any) -> Any:
        return cls.for_object(obj).change_status(obj, action, **kwargs)

    @classmethod
    def move(cls, obj: Any, new_parent: Any, **kwargs: Any) -> Any:
        return cls.for_object(obj).move(obj, new_parent, **kwargs)

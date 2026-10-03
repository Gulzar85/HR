"""Shared helpers for the employee service layer.

Rules every service in this package follows (docs/architecture/employee-domain.md):

* **All-or-nothing.** Every operation is wrapped in ``@transactional``, so a person without an
  employee, or an employee without their code, is never persisted.
* **Permission + audit + event, always.** Authorisation happens in the service, never only in the
  view, so the web UI, the REST API, a management command and the future Electron client are
  governed by the same code.
* **No sensitive values in audit or events.** Identifier and note changes record *that* it happened,
  never the old and new value.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Model

from apps.audit.services import record_audit
from apps.common.exceptions import NotFoundException, PermissionDeniedException, ValidationException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext

EMPLOYEE = "employee"
PERSON = "person"


def actor_or_none(actor: Any) -> Any:
    """``created_by``/``updated_by`` are FKs: an anonymous or unsaved actor becomes ``None``."""
    return actor if getattr(actor, "pk", None) else None


def authorize(actor: Any, permission: str, obj: Any = None) -> None:
    """Permission (model-level or guardian object-level) **and** employee scope.

    ``actor=None`` is a trusted system call. For an ``Employee``/``Person`` target the actor must
    also have it in scope (``apps.employees.scope``); out-of-scope targets raise ``NotFound`` so a
    known UUID reveals nothing (same behaviour as the organization domain). Creating new records
    (``obj=None`` with an ``add`` permission) requires organization-wide access in Phase 3, because
    a new employee has no placement yet that a narrower scope could cover.
    """
    from apps.accounts.services import PermissionService

    from ..models import Employee, Person
    from ..scope import can_access_employee, can_access_person, has_full_access

    if actor is None:
        return
    if not PermissionService.can_access_object(actor, permission, obj):
        raise PermissionDeniedException(
            "You do not have permission to perform this action.", code="permission_denied"
        )
    if isinstance(obj, Employee) and not can_access_employee(actor, obj):
        raise NotFoundException("Employee not found.")
    if isinstance(obj, Person) and not can_access_person(actor, obj):
        raise NotFoundException("Person not found.")
    if obj is None and permission.split(".")[-1].startswith("add_") and not has_full_access(actor):
        raise PermissionDeniedException(
            "Creating employee records requires organization-wide access.",
            code="scope_required",
        )


def require(actor: Any, permission: str, obj: Any = None) -> None:
    """Strict model-level check, for actions whose blast radius is not object-scoped."""
    from apps.accounts.services import PermissionService

    if actor is not None:
        PermissionService.require(actor, permission, obj)


def validate(obj: Model, *, exclude: list[str] | None = None) -> None:
    """Run ``full_clean`` and translate Django's errors into the project's exception envelope."""
    try:
        obj.full_clean(exclude=exclude or [], validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationException(
            "Please correct the highlighted fields.", details=exc.message_dict
        ) from exc


def validator_errors(field_errors: Mapping[str, list[str] | str]) -> ValidationException:
    """Build the standard ``ValidationException`` from ``{field: message(s)}``."""
    details = {
        field: [msg] if isinstance(msg, str) else list(msg) for field, msg in field_errors.items()
    }
    return ValidationException("Please correct the highlighted fields.", details=details)


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """``{field: {"before": x, "after": y}}`` for the fields that actually changed."""
    return {
        key: {"before": before.get(key), "after": new}
        for key, new in after.items()
        if before.get(key) != new
    }


def jsonable(value: Any) -> Any:
    """Audit/timeline payloads are JSON: dates become ISO strings, files their presence."""
    if isinstance(value, date | datetime):
        return value.isoformat()
    if hasattr(value, "name") and hasattr(value, "storage"):  # FieldFile
        return bool(value)
    if hasattr(value, "pk"):
        return str(value.pk)
    return value


def snapshot(obj: Any, fields: tuple[str, ...] | list[str]) -> dict[str, Any]:
    return {f: jsonable(getattr(obj, f, None)) for f in fields}


def coerce_date(value: Any, field: str) -> date | None:
    """Accept ``date`` objects or ISO strings (API/JSON callers); reject anything else cleanly."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise validator_errors({field: "Enter a valid date (YYYY-MM-DD)."}) from exc


def run_validator(validator: Any, value: Any, field: str) -> None:
    """Call a Django field validator and convert its error into the project's envelope."""
    try:
        validator(value)
    except DjangoValidationError as exc:
        raise validator_errors({field: list(exc.messages)}) from exc


def audit(
    *,
    action: str,
    actor: Any,
    obj_type: str,
    obj_id: Any,
    ctx: RequestContext = SYSTEM_CONTEXT,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
    **extra: Any,
) -> None:
    """Write an audit row. ``before``/``after`` must already be free of sensitive values."""
    changes: dict[str, Any] = {}
    if before is not None or after is not None:
        changes = {"before": before or {}, "after": after or {}}
    changes.update(extra)
    record_audit(
        action=f"employees.{action}",
        actor=actor,
        obj_type=obj_type,
        obj_id=str(obj_id),
        changes=changes,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        reason=reason[:255],
    )

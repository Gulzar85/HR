"""``IdentifierService`` - official identity documents (ADR-021).

This is the most sensitive service in the domain. Its contract:

* **Writes** require ``employees.manage_identifiers``; **reads** of the unmasked value require
  ``employees.view_sensitive_identity`` in addition to ``employees.view_identifiers``.
* **Reads are audited** (``employees.identifier_viewed``) - with the identifier *type* only.
* **Audit never stores the value.** A change records ``{"identifier_type": "cnic", "changed": true}``,
  not ``old CNIC = ... / new CNIC = ...``. Old and new values are equally sensitive, so keeping
  either in a log creates a second copy of the secret.
* **Uniqueness** is a database constraint (see ``EmployeeIdentifier.Meta``); the service turns a
  ``IntegrityError`` into a clear, non-leaking ``ConflictException``.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.exceptions import BusinessRuleException, ConflictException, NotFoundException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional
from apps.outbox.services import enqueue_outbox_event

from .. import events, permissions
from ..models import (
    EmployeeIdentifier,
    VerificationStatus,
    normalize_identifier,
)
from .base import (
    EMPLOYEE,
    actor_or_none,
    audit,
    authorize,
    diff,
    jsonable,
    snapshot,
    validate,
    validator_errors,
)
from .timeline_service import record_event

EDITABLE_FIELDS = (
    "identifier_type",
    "value",
    "issuing_country",
    "issue_date",
    "expiry_date",
    "verification_status",
    "is_primary",
    "notes",
)

#: Only these transitions are allowed; anything else is a business-rule violation (422).
VERIFICATION_TRANSITIONS: dict[str, frozenset[str]] = {
    VerificationStatus.UNVERIFIED: frozenset(VerificationStatus.values),
    VerificationStatus.VERIFIED: frozenset(
        {VerificationStatus.EXPIRED, VerificationStatus.REJECTED, VerificationStatus.UNVERIFIED}
    ),
    VerificationStatus.REJECTED: frozenset({VerificationStatus.UNVERIFIED}),
    VerificationStatus.EXPIRED: frozenset(
        {VerificationStatus.UNVERIFIED, VerificationStatus.VERIFIED, VerificationStatus.REJECTED}
    ),
}


class IdentifierService:
    @classmethod
    @transactional
    def add_identifier(
        cls,
        *,
        employee: Any,
        actor: Any,
        data: dict[str, Any],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> EmployeeIdentifier:
        """Attach an identifier to an employee, auditing the fact - not the value."""
        authorize(actor, permissions.MANAGE_IDENTIFIERS, employee)
        fields = _clean(data)
        if not fields.get("value"):
            raise validator_errors({"value": "The identifier value is required."})
        if not fields.get("identifier_type"):
            raise validator_errors({"identifier_type": "Choose an identifier type."})
        fields.setdefault("verification_status", VerificationStatus.UNVERIFIED)
        cls._assert_not_owned_by_another_employee(fields)

        identifier = EmployeeIdentifier(
            employee=employee, **{k: v for k, v in fields.items() if k in EDITABLE_FIELDS}
        )
        validate(identifier)
        identifier.created_by = actor_or_none(actor)
        identifier.updated_by = identifier.created_by
        cls._save(identifier, employee, is_primary=fields.get("is_primary", False))
        audit(
            action="identifier_added",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            before={},
            after={"identifier_type": identifier.identifier_type, "value": "[recorded]"},
            ctx=ctx,
        )
        enqueue_outbox_event(
            events.EmployeeIdentifierAdded(
                employee_id=str(employee.pk),
                employee_code=employee.code,
                identifier_id=str(identifier.pk),
                identifier_type=identifier.identifier_type,
                actor_id=_actor_id(actor),
            ),
            aggregate_type=EMPLOYEE,
            aggregate_id=str(employee.pk),
        )
        record_event(
            employee=employee,
            event_type="identifier_added",
            summary=f"{identifier.get_identifier_type_display()} added",
            actor=actor,
            payload={"identifier_type": identifier.identifier_type},
            is_sensitive=True,
        )
        return identifier

    @classmethod
    @transactional
    def update_identifier(
        cls,
        identifier: EmployeeIdentifier,
        *,
        actor: Any,
        data: dict[str, Any],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> EmployeeIdentifier:
        employee = identifier.employee
        authorize(actor, permissions.MANAGE_IDENTIFIERS, employee)
        fields = _clean(data)
        verification_changed = "verification_status" in fields
        was_primary = identifier.is_primary
        if verification_changed and not cls._verification_allowed(identifier, fields):
            raise BusinessRuleException(
                f"A {identifier.get_verification_status_display().lower()} identifier cannot be "
                f"marked {VerificationStatus(fields['verification_status']).label.lower()}.",
                code="invalid_verification_transition",
            )
        # The value is never captured in the audit snapshot: only whether it changed.
        old_normalized = identifier.normalized_value
        before = {
            "identifier_type": identifier.identifier_type,
            "value": "[recorded]" if identifier.value else "",
            "issuing_country": identifier.issuing_country,
            "issue_date": jsonable(identifier.issue_date),
            "expiry_date": jsonable(identifier.expiry_date),
            "verification_status": identifier.verification_status,
        }
        cls._assert_not_owned_by_another_employee(
            {**snapshot(identifier, ("identifier_type", "issuing_country", "value")), **fields},
            exclude_pk=identifier.pk,
        )
        for key, value in fields.items():
            if key in EDITABLE_FIELDS:
                setattr(identifier, key, value)
        if verification_changed:
            if identifier.verification_status == VerificationStatus.VERIFIED:
                identifier.verified_at = timezone.now()
                identifier.verified_by = actor_or_none(actor)
            else:
                identifier.verified_at = None
                identifier.verified_by = None
        validate(identifier)
        identifier.updated_by = actor_or_none(actor)
        cls._save(identifier, employee, is_primary=fields.get("is_primary", False))
        value_changed = identifier.normalized_value != old_normalized
        after = {
            "identifier_type": identifier.identifier_type,
            "value": "[changed]" if value_changed else ("[recorded]" if identifier.value else ""),
            "issuing_country": identifier.issuing_country,
            "issue_date": jsonable(identifier.issue_date),
            "expiry_date": jsonable(identifier.expiry_date),
            "verification_status": identifier.verification_status,
        }
        changes = diff(before, after)
        if not changes and was_primary == identifier.is_primary:
            return identifier
        audit(
            action="identifier_updated",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            before=before,
            after=after,
            changed=sorted(changes),
            ctx=ctx,
        )
        enqueue_outbox_event(
            events.EmployeeIdentifierUpdated(
                employee_id=str(employee.pk),
                employee_code=employee.code,
                identifier_id=str(identifier.pk),
                identifier_type=identifier.identifier_type,
                actor_id=_actor_id(actor),
            ),
            aggregate_type=EMPLOYEE,
            aggregate_id=str(employee.pk),
        )
        if verification_changed:
            enqueue_outbox_event(
                events.EmployeeIdentifierVerificationChanged(
                    employee_id=str(employee.pk),
                    employee_code=employee.code,
                    identifier_id=str(identifier.pk),
                    identifier_type=identifier.identifier_type,
                    verification_status=identifier.verification_status,
                    actor_id=_actor_id(actor),
                ),
                aggregate_type=EMPLOYEE,
                aggregate_id=str(employee.pk),
            )
            record_event(
                employee=employee,
                event_type="identifier_verification_changed",
                summary=(
                    f"{identifier.get_identifier_type_display()} marked "
                    f"{identifier.get_verification_status_display().lower()}"
                ),
                actor=actor,
                payload={
                    "identifier_type": identifier.identifier_type,
                    "verification_status": identifier.verification_status,
                },
                is_sensitive=True,
            )
        record_event(
            employee=employee,
            event_type="identifier_updated",
            summary=f"{identifier.get_identifier_type_display()} updated",
            actor=actor,
            description=", ".join(sorted(changes)) if changes else "",
            is_sensitive=True,
        )
        return identifier

    @classmethod
    @transactional
    def set_verification(
        cls,
        identifier: EmployeeIdentifier,
        *,
        actor: Any,
        status: str,
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> EmployeeIdentifier:
        """Move an identifier through Unverified → Verified → Rejected/Expired."""
        return cls.update_identifier(
            identifier, actor=actor, data={"verification_status": status}, ctx=ctx
        )

    @classmethod
    @transactional
    def remove_identifier(
        cls,
        identifier: EmployeeIdentifier,
        *,
        actor: Any,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> None:
        """Physically remove an identifier. Reserved for correcting a *wrong* entry: an identifier
        that was genuinely issued stays on the record (marked rejected) so history is preserved."""
        employee = identifier.employee
        authorize(actor, permissions.MANAGE_IDENTIFIERS, employee)
        details = {"identifier_type": identifier.identifier_type}
        with transaction.atomic():
            identifier.delete()
        audit(
            action="identifier_removed",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            before=details,
            after={},
            reason=reason,
            ctx=ctx,
        )
        record_event(
            employee=employee,
            event_type="identifier_updated",
            summary=f"{identifier.get_identifier_type_display()} removed",
            actor=actor,
            payload={"identifier_type": identifier.identifier_type},
            is_sensitive=True,
        )

    # ------------------------------------------------------------------------------ reads
    @classmethod
    def record_read(cls, *, employee: Any, actor: Any, count: int = 1) -> None:
        """Audit that unmasked identifiers were exposed. The value is never part of the record."""
        audit(
            action="identifier_viewed",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            after={"identifier_count": count},
        )

    @classmethod
    def get_for_user(cls, *, actor: Any, identifier_id: Any) -> EmployeeIdentifier:
        identifier = (
            EmployeeIdentifier.objects.select_related("employee__person")
            .filter(pk=identifier_id)
            .first()
        )
        if identifier is None:
            raise NotFoundException("Identifier not found.")
        authorize(actor, permissions.VIEW_IDENTIFIERS, identifier.employee)
        cls.record_read(employee=identifier.employee, actor=actor)
        return identifier

    # ------------------------------------------------------------------------- internals
    @staticmethod
    def _verification_allowed(identifier: EmployeeIdentifier, fields: dict[str, Any]) -> bool:
        target = fields["verification_status"]
        if target == identifier.verification_status:
            return True
        allowed = VERIFICATION_TRANSITIONS.get(identifier.verification_status, frozenset())
        return target in allowed

    @staticmethod
    def _assert_not_owned_by_another_employee(
        fields: dict[str, Any], *, exclude_pk: Any = None
    ) -> None:
        """Pre-flight the database constraint so the user gets a field error, not a 500.

        The message deliberately does not confirm *whose* identifier it is.
        """
        value = fields.get("value")
        if not value:
            return
        clash = EmployeeIdentifier.objects.filter(
            identifier_type=fields.get("identifier_type"),
            issuing_country=(fields.get("issuing_country") or "").upper(),
            normalized_value=normalize_identifier(value),
        ).exclude(verification_status=VerificationStatus.REJECTED)
        if exclude_pk is not None:
            clash = clash.exclude(pk=exclude_pk)
        if clash.exists():
            raise ConflictException(
                "This identifier is already recorded against another employee.",
                details={"value": ["Already in use."]},
                code="identifier_in_use",
            )

    @staticmethod
    def _save(identifier: EmployeeIdentifier, employee: Any, *, is_primary: bool) -> None:
        """Persist, demoting the previous primary of the same type. Constraint is the backstop."""
        with transaction.atomic():
            if is_primary:
                EmployeeIdentifier.objects.filter(
                    employee=employee,
                    identifier_type=identifier.identifier_type,
                    is_primary=True,
                ).exclude(pk=identifier.pk).update(is_primary=False)
            try:
                identifier.save()
            except IntegrityError as exc:
                raise ConflictException(
                    "This identifier could not be saved: the value is already recorded.",
                    details={"value": ["Already in use."]},
                    code="identifier_in_use",
                ) from exc


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key not in EDITABLE_FIELDS or value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        out[key] = value
    return out


def _actor_id(actor: Any) -> str | None:
    return str(actor.pk) if getattr(actor, "pk", None) else None

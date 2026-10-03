"""``EmergencyContactService`` - who to call in an incident.

An employee may have several emergency contacts; at most one is ``is_primary`` (database partial
unique constraint on ``employee``). Reading them requires
``employees.view_emergency_contacts`` - they are third-party personal data, not just employee data.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction

from apps.common.exceptions import ConflictException, NotFoundException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional
from apps.outbox.services import enqueue_outbox_event

from .. import events, permissions
from ..models import EmergencyContact
from .base import (
    EMPLOYEE,
    actor_or_none,
    audit,
    authorize,
    diff,
    snapshot,
    validate,
    validator_errors,
)
from .timeline_service import record_event

EDITABLE_FIELDS = (
    "name",
    "relationship",
    "phone",
    "alternative_phone",
    "email",
    "address",
    "notes",
    "is_primary",
)
REQUIRED_FIELDS = ("name", "relationship", "phone")

#: Fields safe to write into an audit row. Name / phone / email are third-party personal data and
#: are deliberately excluded.
AUDITED_FIELDS = ("relationship", "is_primary")


class EmergencyContactService:
    @classmethod
    @transactional
    def add_emergency_contact(
        cls,
        *,
        employee: Any,
        actor: Any,
        data: dict[str, Any],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> EmergencyContact:
        authorize(actor, permissions.MANAGE_EMERGENCY_CONTACTS, employee)
        fields = _clean(data)
        errors = {f: "This field is required." for f in REQUIRED_FIELDS if not fields.get(f)}
        if errors:
            raise validator_errors(errors)
        if fields.get("is_primary") and cls._has_primary(employee):
            raise ConflictException(
                "This employee already has a primary emergency contact. Make that one "
                "non-primary first.",
                details={"is_primary": ["Only one primary emergency contact is allowed."]},
                code="duplicate_primary_emergency_contact",
            )
        contact = EmergencyContact(
            employee=employee, **{k: v for k, v in fields.items() if k in EDITABLE_FIELDS}
        )
        validate(contact)
        contact.created_by = actor_or_none(actor)
        contact.updated_by = contact.created_by
        cls._save(contact, employee)
        audit(
            action="emergency_contact_added",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            after=snapshot(contact, AUDITED_FIELDS),
            ctx=ctx,
        )
        enqueue_outbox_event(
            events.EmergencyContactAdded(
                employee_id=str(employee.pk),
                employee_code=employee.code,
                emergency_contact_id=str(contact.pk),
                actor_id=_actor_id(actor),
            ),
            aggregate_type=EMPLOYEE,
            aggregate_id=str(employee.pk),
        )
        record_event(
            employee=employee,
            event_type="emergency_contact_added",
            summary=f"Emergency contact added ({contact.get_relationship_display().lower()})",
            actor=actor,
            payload={"relationship": contact.relationship},
        )
        return contact

    @classmethod
    @transactional
    def update_emergency_contact(
        cls,
        contact: EmergencyContact,
        *,
        actor: Any,
        data: dict[str, Any],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> EmergencyContact:
        employee = contact.employee
        authorize(actor, permissions.MANAGE_EMERGENCY_CONTACTS, employee)
        fields = _clean(data)
        if fields.get("is_primary") and not contact.is_primary:
            cls._assert_no_other_primary(employee, exclude_pk=contact.pk)
        before = snapshot(contact, EDITABLE_FIELDS)
        for key, value in fields.items():
            setattr(contact, key, value)
        validate(contact)
        contact.updated_by = actor_or_none(actor)
        cls._save(contact, employee)
        after = snapshot(contact, EDITABLE_FIELDS)
        changes = diff(before, after)
        if not changes:
            return contact
        # The audit row carries the *structure* of the change, never the contact's details.
        audit(
            action="emergency_contact_updated",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            before=_masked(before),
            after=_masked(after),
            changed=sorted(changes),
            ctx=ctx,
        )
        enqueue_outbox_event(
            events.EmergencyContactUpdated(
                employee_id=str(employee.pk),
                employee_code=employee.code,
                emergency_contact_id=str(contact.pk),
                actor_id=_actor_id(actor),
            ),
            aggregate_type=EMPLOYEE,
            aggregate_id=str(employee.pk),
        )
        record_event(
            employee=employee,
            event_type="emergency_contact_updated",
            summary="Emergency contact updated",
            actor=actor,
            description=", ".join(sorted(changes)),
        )
        return contact

    @classmethod
    @transactional
    def remove_emergency_contact(
        cls,
        contact: EmergencyContact,
        *,
        actor: Any,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> None:
        employee = contact.employee
        authorize(actor, permissions.MANAGE_EMERGENCY_CONTACTS, employee)
        details = snapshot(contact, AUDITED_FIELDS)
        with transaction.atomic():
            contact.delete()
        audit(
            action="emergency_contact_removed",
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
            event_type="emergency_contact_removed",
            summary="Emergency contact removed",
            actor=actor,
        )

    @classmethod
    def get_for_user(cls, *, actor: Any, emergency_contact_id: Any) -> EmergencyContact:
        contact = (
            EmergencyContact.objects.select_related("employee__person")
            .filter(pk=emergency_contact_id)
            .first()
        )
        if contact is None:
            raise NotFoundException("Emergency contact not found.")
        authorize(actor, permissions.MANAGE_EMERGENCY_CONTACTS, contact.employee)
        return contact

    # ------------------------------------------------------------------------- internals
    @staticmethod
    def _has_primary(employee: Any, exclude_pk: Any = None) -> bool:
        qs = EmergencyContact.objects.filter(employee=employee, is_primary=True)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        return qs.exists()

    @classmethod
    def _assert_no_other_primary(cls, employee: Any, *, exclude_pk: Any) -> None:
        if cls._has_primary(employee, exclude_pk=exclude_pk):
            raise ConflictException(
                "This employee already has a primary emergency contact. Make that one "
                "non-primary first.",
                details={"is_primary": ["Only one primary emergency contact is allowed."]},
                code="duplicate_primary_emergency_contact",
            )

    @staticmethod
    def _save(contact: EmergencyContact, employee: Any) -> None:
        with transaction.atomic():
            if contact.is_primary:
                EmergencyContact.objects.filter(employee=employee, is_primary=True).exclude(
                    pk=contact.pk
                ).update(is_primary=False)
            try:
                contact.save()
            except IntegrityError as exc:
                raise ConflictException(
                    "Only one primary emergency contact is allowed.",
                    details={"is_primary": ["Only one primary emergency contact is allowed."]},
                    code="duplicate_primary_emergency_contact",
                ) from exc


def _masked(values: dict[str, Any]) -> dict[str, Any]:
    """Replace contact details with a placeholder; keep structure and flags."""
    return {
        key: (value if key in AUDITED_FIELDS else "[recorded]" if value else "")
        for key, value in values.items()
    }


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key not in EDITABLE_FIELDS or value is None:
            continue
        out[key] = value.strip() if isinstance(value, str) else value
    return out


def _actor_id(actor: Any) -> str | None:
    return str(actor.pk) if getattr(actor, "pk", None) else None

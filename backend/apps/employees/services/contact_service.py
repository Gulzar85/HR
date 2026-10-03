"""``ContactService`` - phone and email channels.

"Primary" means *the current one of its type*, not *the* primary contact: an employee normally has
one primary mobile **and** one primary email. The rule is a partial unique constraint in the
database; the service additionally demotes the previous primary inside the same transaction, so a
change is atomic from the reader's point of view.

Contact values are personal data, so the list/detail screens only show them to holders of
``employees.view_sensitive_contacts`` (enforced in the views and serializers, never in the model).
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction

from apps.common.exceptions import ConflictException, NotFoundException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional
from apps.outbox.services import enqueue_outbox_event

from .. import events, permissions
from ..models import Contact, ContactType
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

EDITABLE_FIELDS = ("contact_type", "value", "label", "is_primary", "is_verified")


class ContactService:
    @classmethod
    @transactional
    def add_contact(
        cls,
        *,
        employee: Any,
        actor: Any,
        data: dict[str, Any],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Contact:
        authorize(actor, permissions.MANAGE_CONTACTS, employee)
        fields = _clean(data)
        cls._require_type_and_value(fields)
        contact = Contact(
            employee=employee, **{k: v for k, v in fields.items() if k in EDITABLE_FIELDS}
        )
        validate(contact)
        contact.created_by = actor_or_none(actor)
        contact.updated_by = contact.created_by
        cls._save(contact, employee)
        audit(
            action="contact_added",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            after=snapshot(contact, ("contact_type", "label", "is_primary", "is_verified")),
            ctx=ctx,
        )
        enqueue_outbox_event(
            events.EmployeeContactAdded(
                employee_id=str(employee.pk),
                employee_code=employee.code,
                contact_id=str(contact.pk),
                contact_type=contact.contact_type,
                actor_id=_actor_id(actor),
            ),
            aggregate_type=EMPLOYEE,
            aggregate_id=str(employee.pk),
        )
        record_event(
            employee=employee,
            event_type="contact_added",
            summary=f"{contact.get_contact_type_display()} added",
            actor=actor,
            payload={"contact_type": contact.contact_type},
        )
        return contact

    @classmethod
    @transactional
    def update_contact(
        cls,
        contact: Contact,
        *,
        actor: Any,
        data: dict[str, Any],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Contact:
        employee = contact.employee
        authorize(actor, permissions.MANAGE_CONTACTS, employee)
        fields = _clean(data)
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
        audit(
            action="contact_updated",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            before=before,
            after=after,
            ctx=ctx,
        )
        enqueue_outbox_event(
            events.EmployeeContactUpdated(
                employee_id=str(employee.pk),
                employee_code=employee.code,
                contact_id=str(contact.pk),
                contact_type=contact.contact_type,
                actor_id=_actor_id(actor),
            ),
            aggregate_type=EMPLOYEE,
            aggregate_id=str(employee.pk),
        )
        record_event(
            employee=employee,
            event_type="contact_updated",
            summary=f"{contact.get_contact_type_display()} updated",
            actor=actor,
            description=", ".join(sorted(changes)),
            payload={"contact_type": contact.contact_type},
        )
        return contact

    @classmethod
    @transactional
    def set_primary(
        cls, contact: Contact, *, actor: Any, ctx: RequestContext = SYSTEM_CONTEXT
    ) -> Contact:
        """Make this the primary contact of its type (used by the inline HTMX action)."""
        if contact.is_primary:
            return contact
        return cls.update_contact(contact, actor=actor, data={"is_primary": True}, ctx=ctx)

    @classmethod
    @transactional
    def remove_contact(
        cls,
        contact: Contact,
        *,
        actor: Any,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> None:
        employee = contact.employee
        authorize(actor, permissions.MANAGE_CONTACTS, employee)
        details = snapshot(contact, ("contact_type", "is_primary"))
        with transaction.atomic():
            contact.delete()
        audit(
            action="contact_removed",
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
            event_type="contact_removed",
            summary=f"{ContactType(details['contact_type']).label} removed",
            actor=actor,
            payload={"contact_type": details["contact_type"]},
        )

    @classmethod
    def get_for_user(cls, *, actor: Any, contact_id: Any) -> Contact:
        contact = Contact.objects.select_related("employee__person").filter(pk=contact_id).first()
        if contact is None:
            raise NotFoundException("Contact not found.")
        authorize(actor, permissions.MANAGE_CONTACTS, contact.employee)
        return contact

    # ------------------------------------------------------------------------- internals
    @staticmethod
    def _require_type_and_value(fields: dict[str, Any]) -> None:
        errors: dict[str, str] = {}
        if not fields.get("contact_type"):
            errors["contact_type"] = "Choose a contact type."
        if not fields.get("value"):
            errors["value"] = "A value is required."
        if errors:
            raise validator_errors(errors)

    @staticmethod
    def _save(contact: Contact, employee: Any) -> None:
        with transaction.atomic():
            if contact.is_primary:
                Contact.objects.filter(
                    employee=employee,
                    contact_type=contact.contact_type,
                    is_primary=True,
                ).exclude(pk=contact.pk).update(is_primary=False)
            try:
                contact.save()
            except IntegrityError as exc:
                raise ConflictException(
                    "Only one contact of each type can be primary.",
                    details={"is_primary": ["Another contact of this type is already primary."]},
                    code="duplicate_primary_contact",
                ) from exc


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key not in EDITABLE_FIELDS or value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        if value == "" and key in ("label",):
            value = ""
        out[key] = value
    return out


def _actor_id(actor: Any) -> str | None:
    return str(actor.pk) if getattr(actor, "pk", None) else None

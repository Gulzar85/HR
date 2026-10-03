"""``PersonService`` - writes to the human identity record.

``Person`` is reusable on purpose (docs/adr/ADR-018): recruitment will "hire" into an existing person
rather than duplicating identity, so creating a person is a first-class operation and not a side
effect of creating an employee.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction

from apps.common.exceptions import ConflictException, NotFoundException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional
from apps.outbox.services import enqueue_outbox_event

from .. import events, permissions
from ..models import Person
from ..validators import validate_date_of_birth, validate_profile_photo
from .base import (
    PERSON,
    actor_or_none,
    audit,
    authorize,
    coerce_date,
    diff,
    run_validator,
    snapshot,
    validate,
    validator_errors,
)
from .timeline_service import record_event

NAME_FIELDS = ("first_name", "middle_name", "last_name", "preferred_name")
SENSITIVE_FIELDS = ("date_of_birth", "gender", "nationality")
EDITABLE_FIELDS = (*NAME_FIELDS, *SENSITIVE_FIELDS)


class PersonService:
    """Business operations on ``Person``. No HTTP, no templates."""

    @classmethod
    @transactional
    def create_person(
        cls,
        *,
        actor: Any = None,
        data: dict[str, Any],
        profile_photo: Any = None,
        remove_photo: bool = False,
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Person:
        """Create a person. ``data`` may contain any of :data:`EDITABLE_FIELDS`.

        The first name and last name are required; everything else is optional so a record can be
        captured even when information is still missing.
        """
        authorize(actor, permissions.ADD_PERSON)
        fields = {k: _clean_text(v) for k, v in data.items() if k in EDITABLE_FIELDS}
        _require_names(fields)
        if "date_of_birth" in fields:
            fields["date_of_birth"] = coerce_date(fields["date_of_birth"], "date_of_birth")
            run_validator(validate_date_of_birth, fields["date_of_birth"], "date_of_birth")
        if profile_photo:
            run_validator(validate_profile_photo, profile_photo, "profile_photo")
        person = Person(**fields)
        validate(person, exclude=["profile_photo"])
        if profile_photo or remove_photo:
            person.profile_photo = profile_photo or None
        person.created_by = actor_or_none(actor)
        person.updated_by = person.created_by
        try:
            with transaction.atomic():
                person.save()
        except IntegrityError as exc:  # pragma: no cover - only reachable via raw writes
            raise ConflictException("This person could not be saved.") from exc
        audit(
            action="person_created",
            actor=actor,
            obj_type=PERSON,
            obj_id=person.pk,
            after=snapshot(person, NAME_FIELDS),
            sensitive_fields_set=sorted(f for f in SENSITIVE_FIELDS if getattr(person, f)),
            photo=bool(person.profile_photo),
            ctx=ctx,
        )
        enqueue_outbox_event(
            events.PersonCreated(person_id=str(person.pk), actor_id=_actor_id(actor)),
            aggregate_type=PERSON,
            aggregate_id=str(person.pk),
        )
        return person

    @classmethod
    @transactional
    def update_person(
        cls,
        person: Person,
        *,
        actor: Any = None,
        data: dict[str, Any],
        profile_photo: Any = None,
        remove_photo: bool = False,
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Person:
        """Update identity fields and/or the photo. Returns the same instance, refreshed."""
        authorize(actor, permissions.CHANGE_PERSON, person)
        fields = {k: _clean_text(v) for k, v in data.items() if k in EDITABLE_FIELDS}
        if "date_of_birth" in fields:
            fields["date_of_birth"] = coerce_date(fields["date_of_birth"], "date_of_birth")
            run_validator(validate_date_of_birth, fields["date_of_birth"], "date_of_birth")
        sensitive_changes = [
            f for f in SENSITIVE_FIELDS if f in fields and fields[f] != getattr(person, f)
        ]
        if sensitive_changes or profile_photo or remove_photo:
            # Sensitive identity is edited only by those allowed to see it (ADR-021).
            authorize(actor, permissions.VIEW_SENSITIVE_IDENTITY, person)
        if profile_photo:
            run_validator(validate_profile_photo, profile_photo, "profile_photo")
        before = snapshot(person, EDITABLE_FIELDS)
        for key, value in fields.items():
            setattr(person, key, value)
        validate(person, exclude=["profile_photo"])
        photo_change = ""
        if remove_photo and person.profile_photo:
            photo_change = "removed"
            person.delete_photo()
        elif profile_photo:
            photo_change = "replaced" if person.profile_photo else "added"
            person.replace_photo(profile_photo)
        person.updated_by = actor_or_none(actor)
        person.save()
        changes = diff(before, snapshot(person, EDITABLE_FIELDS))
        if not changes and not photo_change:
            return person
        # Names are recorded before/after; sensitive identity fields only by *name* (no values).
        audit(
            action="person_updated",
            actor=actor,
            obj_type=PERSON,
            obj_id=person.pk,
            before={k: v["before"] for k, v in changes.items() if k in NAME_FIELDS},
            after={k: v["after"] for k, v in changes.items() if k in NAME_FIELDS},
            sensitive_fields_changed=sorted(k for k in changes if k in SENSITIVE_FIELDS),
            photo=photo_change,
            ctx=ctx,
        )
        enqueue_outbox_event(
            events.PersonUpdated(person_id=str(person.pk), actor_id=_actor_id(actor)),
            aggregate_type=PERSON,
            aggregate_id=str(person.pk),
        )
        employee = getattr(person, "employee", None)
        if employee is not None:
            record_event(
                employee=employee,
                event_type="person_updated",
                summary="Personal details updated",
                actor=actor,
                description=", ".join(sorted(changes)) or "Profile photo changed",
                payload={"fields": sorted(changes)} if changes else {},
                is_sensitive=bool(changes.get("date_of_birth") or changes.get("nationality")),
            )
            if photo_change == "removed":
                record_event(
                    employee=employee,
                    event_type="photo_removed",
                    summary="Profile photo removed",
                    actor=actor,
                )
        return person

    @classmethod
    def get_for_user(cls, *, actor: Any, person_id: Any) -> Person:
        """Read one person the actor may see. Raises ``NotFoundException`` otherwise (no oracle)."""
        person = Person.objects.filter(pk=person_id).first()
        if person is None:
            raise NotFoundException("Person not found.")
        authorize(actor, permissions.VIEW_PERSON, person)
        return person

    @classmethod
    def find_by_national_id(cls, *, identifier_type: str, value: str, issuing_country: str = ""):
        """Lookup used by the future ``HireService`` to *reuse* a person instead of duplicating one."""
        from ..models import normalize_identifier

        return (
            Person.objects.filter(
                employee__identifiers__identifier_type=identifier_type,
                employee__identifiers__normalized_value=normalize_identifier(value),
                employee__identifiers__issuing_country=(issuing_country or "").upper(),
            )
            .exclude(employee__identifiers__verification_status="rejected")
            .distinct()
            .first()
        )


def _clean_text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _require_names(fields: dict[str, Any]) -> None:
    errors: dict[str, str] = {}
    if not fields.get("first_name"):
        errors["first_name"] = "First name is required."
    if not fields.get("last_name"):
        errors["last_name"] = "Last name is required."
    if errors:
        raise validator_errors(errors)


def _actor_id(actor: Any) -> str | None:
    return str(actor.pk) if getattr(actor, "pk", None) else None

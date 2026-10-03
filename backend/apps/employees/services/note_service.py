"""``NoteService`` and ``RelationshipService`` - the two small auxiliary record types.

Both are intentionally thin. Notes are short internal annotations with a visibility flag (formal case
handling belongs to HR Cases in Phase 8+); relationships are controlled typed links between two
people (no inferred family graph - see docs/architecture/employee-domain.md).
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction

from apps.common.exceptions import ConflictException, NotFoundException, ValidationException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional

from .. import permissions
from ..models import EmployeeNote, NoteVisibility, PersonRelationship
from .base import (
    EMPLOYEE,
    PERSON,
    actor_or_none,
    audit,
    authorize,
    snapshot,
    validate,
    validator_errors,
)
from .timeline_service import record_event

NOTE_FIELDS = ("content", "visibility", "pinned")
RELATIONSHIP_FIELDS = ("relationship_type", "notes")


class NoteService:
    @classmethod
    @transactional
    def add_note(
        cls,
        *,
        employee: Any,
        actor: Any,
        data: dict[str, Any],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> EmployeeNote:
        authorize(actor, permissions.MANAGE_NOTES, employee)
        content = (data.get("content") or "").strip()
        if not content:
            raise validator_errors({"content": "Write something before saving."})
        visibility = data.get("visibility") or NoteVisibility.INTERNAL
        if visibility == NoteVisibility.RESTRICTED:
            # Writing a restricted note is itself a privileged act.
            authorize(actor, permissions.VIEW_SENSITIVE_IDENTITY, employee)
        note = EmployeeNote(
            employee=employee,
            content=content,
            visibility=visibility,
            pinned=bool(data.get("pinned")),
        )
        validate(note)
        note.created_by = actor_or_none(actor)
        note.updated_by = note.created_by
        note.save()
        # The note body is never written to the audit log - only that one was added.
        audit(
            action="note_added",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            after={"visibility": note.visibility, "pinned": note.pinned},
            ctx=ctx,
        )
        record_event(
            employee=employee,
            event_type="note_added",
            summary=f"Note added ({note.get_visibility_display().split(' (')[0].lower()})",
            actor=actor,
            payload={"visibility": note.visibility},
            is_sensitive=note.is_restricted,
        )
        return note

    @classmethod
    @transactional
    def remove_note(
        cls,
        note: EmployeeNote,
        *,
        actor: Any,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> None:
        employee = note.employee
        authorize(actor, permissions.MANAGE_NOTES, employee)
        if note.is_restricted:
            authorize(actor, permissions.VIEW_SENSITIVE_IDENTITY, employee)
        details = {
            "visibility": note.visibility,
            "pinned": note.pinned,
            "created_by": str(note.created_by_id or ""),
        }
        with transaction.atomic():
            note.delete()
        audit(
            action="note_removed",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            before=details,
            after={},
            reason=reason,
            ctx=ctx,
        )
        record_event(
            employee=employee, event_type="note_removed", summary="Note removed", actor=actor
        )


class RelationshipService:
    @classmethod
    @transactional
    def add_relationship(
        cls,
        *,
        from_person: Any,
        actor: Any,
        to_person: Any,
        relationship_type: str,
        notes: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> PersonRelationship:
        authorize(actor, permissions.MANAGE_RELATIONSHIPS, from_person)
        if not relationship_type:
            raise validator_errors({"relationship_type": "Choose a relationship type."})
        if to_person.pk == from_person.pk:
            raise ValidationException(
                "A person cannot be related to themselves.",
                details={"to_person": ["Choose a different person."]},
            )
        relationship = PersonRelationship(
            from_person=from_person,
            to_person=to_person,
            relationship_type=relationship_type,
            notes=(notes or "").strip()[:255],
        )
        validate(relationship)
        relationship.created_by = actor_or_none(actor)
        relationship.updated_by = relationship.created_by
        try:
            with transaction.atomic():
                relationship.save()
        except IntegrityError as exc:
            raise ConflictException(
                "This relationship is already recorded.", code="duplicate_relationship"
            ) from exc
        audit(
            action="relationship_added",
            actor=actor,
            obj_type=PERSON,
            obj_id=from_person.pk,
            after={
                **snapshot(relationship, RELATIONSHIP_FIELDS),
                "to_person": str(to_person.pk),
            },
            ctx=ctx,
        )
        employee = getattr(from_person, "employee", None)
        if employee is not None:
            record_event(
                employee=employee,
                event_type="relationship_added",
                summary=(
                    f"Relationship added ({relationship.get_relationship_type_display().lower()})"
                ),
                actor=actor,
                payload={"relationship_type": relationship.relationship_type},
            )
        return relationship

    @classmethod
    @transactional
    def remove_relationship(
        cls,
        relationship: PersonRelationship,
        *,
        actor: Any,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> None:
        from_person = relationship.from_person
        authorize(actor, permissions.MANAGE_RELATIONSHIPS, from_person)
        details = {
            **snapshot(relationship, RELATIONSHIP_FIELDS),
            "to_person": str(relationship.to_person_id),
        }
        with transaction.atomic():
            relationship.delete()
        audit(
            action="relationship_removed",
            actor=actor,
            obj_type=PERSON,
            obj_id=from_person.pk,
            before=details,
            after={},
            reason=reason,
            ctx=ctx,
        )
        employee = getattr(from_person, "employee", None)
        if employee is not None:
            record_event(
                employee=employee,
                event_type="relationship_removed",
                summary="Relationship removed",
                actor=actor,
            )

    @classmethod
    def get_for_user(cls, *, actor: Any, relationship_id: Any) -> PersonRelationship:
        relationship = (
            PersonRelationship.objects.select_related("from_person", "to_person")
            .filter(pk=relationship_id)
            .first()
        )
        if relationship is None:
            raise NotFoundException("Relationship not found.")
        authorize(actor, permissions.MANAGE_RELATIONSHIPS, relationship.from_person)
        return relationship

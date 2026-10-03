"""Timeline writer - the shared history foundation for the employee domain.

Every domain that changes something about an employee records an entry here, so the employee page
shows one chronological history. Phase 3 uses it for person/employee/identifier/contact/address/
emergency-contact/note/user-link changes; Phase 4+ adds Employment, Assignment and Position events
by calling :func:`record_event` with ``source_app="assignments"`` and an event type this table
already accepts (or after extending :class:`TimelineEntry.EventType`).

Two properties matter more than the feature itself:

* **Best effort.** A timeline write must never fail the business operation that triggered it. The
  caller is inside a transaction; an exception here would roll back a valid employee creation.
  Failures are logged and swallowed.
* **Safe payloads.** ``payload`` is rendered in the UI and serialized in the API, so it must never
  contain a national identifier, a full contact value or note text. Services pass type/status codes.
"""

from __future__ import annotations

from typing import Any

from django.db import DatabaseError
from django.db.models import QuerySet

from apps.common.exceptions import NotFoundException, PermissionDeniedException
from apps.common.logging import get_logger
from apps.common.request_context import RequestContext

from .. import permissions
from ..models import Employee, TimelineEntry
from .base import authorize

logger = get_logger("app")

SOURCE_APP = "employees"


def record_event(
    *,
    employee: Any,
    event_type: str,
    summary: str,
    actor: Any = None,
    description: str = "",
    payload: dict[str, Any] | None = None,
    is_sensitive: bool = False,
    occurred_on: str | None = None,
    source_app: str = SOURCE_APP,
    ctx: RequestContext | None = None,
) -> TimelineEntry | None:
    """Append one entry. Returns ``None`` (and logs) instead of raising - see module docstring."""
    try:
        return TimelineEntry.objects.create(
            employee_id=employee.pk if hasattr(employee, "pk") else employee,
            event_type=event_type,
            summary=summary[:255],
            description=description,
            payload=payload or {},
            is_sensitive=is_sensitive,
            source_app=source_app,
            actor=actor if getattr(actor, "pk", None) else None,
        )
    except DatabaseError:
        logger.exception(
            "timeline_write_failed",
            extra={"event_type": event_type, "employee": str(getattr(employee, "pk", employee))},
        )
        return None
    except (ValueError, TypeError):
        logger.exception("timeline_write_invalid", extra={"event_type": event_type})
        return None


class TimelineService:
    """The read side of the timeline.

    The timeline is a cross-domain view of one employee's history, so it needs its own authorization
    step rather than relying on the caller having already checked the employee. Sensitive entries -
    anything written with ``is_sensitive=True``, which is where identifier and restricted-note
    changes land - are hidden from actors without ``employees.view_sensitive_identity``.
    """

    @classmethod
    def list_for_user(
        cls,
        *,
        actor: Any,
        employee: Any,
        event_type: str = "",
        include_sensitive: bool | None = None,
    ) -> QuerySet[TimelineEntry]:
        authorize(actor, permissions.VIEW_TIMELINE, employee)
        qs = TimelineEntry.objects.filter(employee=employee).order_by("-occurred_at")
        if event_type:
            qs = qs.filter(event_type=event_type)
        want_sensitive = (
            cls._may_see_sensitive(actor, employee)
            if include_sensitive is None
            else include_sensitive
        )
        if not want_sensitive:
            qs = qs.filter(is_sensitive=False)
        return qs

    @classmethod
    def get_employee_for_user(cls, *, actor: Any, employee_id: Any) -> Employee:
        employee = Employee.objects.select_related("person").filter(pk=employee_id).first()
        if employee is None:
            raise NotFoundException("Employee not found.")
        authorize(actor, permissions.VIEW_TIMELINE, employee)
        return employee

    @staticmethod
    def _may_see_sensitive(actor: Any, employee: Any) -> bool:
        try:
            authorize(actor, permissions.VIEW_SENSITIVE_IDENTITY, employee)
        except PermissionDeniedException:
            return False
        return True

"""``AddressService`` - effective-dated postal addresses.

Addresses are never overwritten. Recording a new address of a type that already has a current one:

1. closes the previous row (``effective_to`` = day before the new one starts), keeping it readable
   as history and flipping ``is_primary`` off;
2. opens the new row with ``effective_from`` and ``is_primary=True``.

"Which address was current on date X?" therefore stays answerable, which is what payroll, delivery
and audit need later (docs/architecture/employee-domain.md, section "Address history"). The model is
deliberately simple temporal data - no interval tables.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import IntegrityError, transaction

from apps.common.exceptions import BusinessRuleException, ConflictException, NotFoundException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional
from apps.common.utils import today_local
from apps.outbox.services import enqueue_outbox_event

from .. import events, permissions
from ..models import Address
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
    "address_type",
    "address_line_1",
    "address_line_2",
    "city",
    "state_province",
    "postal_code",
    "country",
    "effective_from",
    "effective_to",
)
REQUIRED_FIELDS = ("address_type", "address_line_1", "city")


class AddressService:
    @classmethod
    @transactional
    def add_address(
        cls,
        *,
        employee: Any,
        actor: Any,
        data: dict[str, Any],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Address:
        """Record an address. ``effective_from`` defaults to today; setting it also closes the
        address it replaces when the previous one starts on or before that date."""
        authorize(actor, permissions.MANAGE_ADDRESSES, employee)
        fields = _clean(data)
        errors = {f: "This field is required." for f in REQUIRED_FIELDS if not fields.get(f)}
        if errors:
            raise validator_errors(errors)
        effective_from = fields.get("effective_from") or today_local()
        previous = cls._current_of_type(employee, fields["address_type"])
        address = Address(
            employee=employee,
            **{k: v for k, v in fields.items() if k in EDITABLE_FIELDS},
            is_primary=True,
        )
        address.effective_from = effective_from
        validate(address)
        address.created_by = actor_or_none(actor)
        address.updated_by = address.created_by
        with transaction.atomic():
            superseded = cls._close_previous(previous, effective_from, actor)
            try:
                address.save()
            except IntegrityError as exc:
                raise ConflictException(
                    "Only one current address of each type is allowed.",
                    details={"address_type": ["Another current address of this type exists."]},
                    code="duplicate_primary_address",
                ) from exc
        audit(
            action="address_added",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            before={},
            after=snapshot(address, ("address_type", "city", "effective_from")),
            superseded=str(superseded.pk) if superseded else "",
            ctx=ctx,
        )
        enqueue_outbox_event(
            events.EmployeeAddressChanged(
                employee_id=str(employee.pk),
                employee_code=employee.code,
                address_id=str(address.pk),
                address_type=address.address_type,
                actor_id=_actor_id(actor),
            ),
            aggregate_type=EMPLOYEE,
            aggregate_id=str(employee.pk),
        )
        record_event(
            employee=employee,
            event_type="address_added",
            summary=f"{address.get_address_type_display()} recorded",
            actor=actor,
            payload={"address_type": address.address_type, "city": address.city},
        )
        if superseded is not None:
            record_event(
                employee=employee,
                event_type="address_ended",
                summary=f"Previous {superseded.get_address_type_display().lower()} closed",
                actor=actor,
                payload={"address_type": superseded.address_type},
            )
        return address

    @classmethod
    @transactional
    def update_address(
        cls,
        address: Address,
        *,
        actor: Any,
        data: dict[str, Any],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Address:
        """Correct an address in place.

        A *correction* (typo in the street, wrong postal code) is an update. A genuine *move* is
        :meth:`add_address` with the same ``address_type``, which preserves the previous address as
        history. Editing the current address in place is therefore safe; editing a closed
        (historical) address is refused so history cannot be rewritten.
        """
        employee = address.employee
        authorize(actor, permissions.MANAGE_ADDRESSES, employee)
        if not address.is_current and address.effective_to is not None:
            raise BusinessRuleException(
                "This address is closed history and cannot be edited. Record a new address instead.",
                code="address_closed",
            )
        fields = _clean(data)
        before = snapshot(address, EDITABLE_FIELDS)
        for key, value in fields.items():
            setattr(address, key, value)
        validate(address)
        address.updated_by = actor_or_none(actor)
        address.save()
        after = snapshot(address, EDITABLE_FIELDS)
        changes = diff(before, after)
        if not changes:
            return address
        # Private address lines are never copied into the audit log: changed field *names* only,
        # plus the non-identifying type/city/dates.
        public = ("address_type", "city", "country", "effective_from", "effective_to")
        audit(
            action="address_updated",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            before={k: v for k, v in before.items() if k in public},
            after={k: v for k, v in after.items() if k in public},
            changed=sorted(changes),
            ctx=ctx,
        )
        enqueue_outbox_event(
            events.EmployeeAddressChanged(
                employee_id=str(employee.pk),
                employee_code=employee.code,
                address_id=str(address.pk),
                address_type=address.address_type,
                actor_id=_actor_id(actor),
            ),
            aggregate_type=EMPLOYEE,
            aggregate_id=str(employee.pk),
        )
        record_event(
            employee=employee,
            event_type="address_changed",
            summary=f"{address.get_address_type_display()} updated",
            actor=actor,
            description=", ".join(sorted(changes)),
            payload={"address_type": address.address_type},
        )
        return address

    @classmethod
    @transactional
    def close_address(
        cls,
        address: Address,
        *,
        actor: Any,
        effective_to: Any = None,
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Address:
        """End an address without deleting it (the address stops being current)."""
        employee = address.employee
        authorize(actor, permissions.MANAGE_ADDRESSES, employee)
        end = effective_to or today_local()
        if address.effective_from and end < address.effective_from:
            raise BusinessRuleException(
                "An address cannot end before it started.", code="invalid_effective_range"
            )
        address.effective_to = end
        address.is_primary = False
        address.updated_by = actor_or_none(actor)
        address.save(update_fields=["effective_to", "is_primary", "updated_by", "updated_at"])
        audit(
            action="address_closed",
            actor=actor,
            obj_type=EMPLOYEE,
            obj_id=employee.pk,
            before={"effective_to": None, "is_primary": True},
            after={"effective_to": end, "is_primary": False},
            reason=reason,
            ctx=ctx,
        )
        record_event(
            employee=employee,
            event_type="address_ended",
            summary=f"{address.get_address_type_display()} closed",
            actor=actor,
            payload={"address_type": address.address_type, "effective_to": str(end)},
        )
        return address

    @classmethod
    def get_for_user(cls, *, actor: Any, address_id: Any) -> Address:
        address = Address.objects.select_related("employee__person").filter(pk=address_id).first()
        if address is None:
            raise NotFoundException("Address not found.")
        authorize(actor, permissions.MANAGE_ADDRESSES, address.employee)
        return address

    # ------------------------------------------------------------------------- internals
    @staticmethod
    def _current_of_type(employee: Any, address_type: str) -> Address | None:
        """The open address of this type, if any - the row a new address supersedes."""
        return (
            Address.objects.filter(
                employee=employee, address_type=address_type, effective_to__isnull=True
            )
            .order_by("-effective_from")
            .first()
        )

    @staticmethod
    def _close_previous(
        previous: Address | None, effective_from: Any, actor: Any
    ) -> Address | None:
        """Close ``previous`` the day before ``effective_from``. Never rewrites future history."""
        if previous is None:
            return None
        new_end = effective_from - timedelta(days=1)
        if previous.effective_from and new_end < previous.effective_from:
            # The existing address starts after the new one does: refuse rather than produce a
            # timeline that reads backwards.
            raise BusinessRuleException(
                f"The existing {previous.get_address_type_display().lower()} starts on "
                f"{previous.effective_from:%d %b %Y}, after the new address's start date.",
                code="effective_from_before_existing",
                details={
                    "effective_from": ["Must be on or after the current address's start date."]
                },
            )
        previous.effective_to = new_end
        previous.is_primary = False
        previous.updated_by = actor_or_none(actor)
        previous.save(update_fields=["effective_to", "is_primary", "updated_by", "updated_at"])
        return previous


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key not in EDITABLE_FIELDS or value is None:
            continue
        out[key] = value.strip() if isinstance(value, str) else value
    return out


def _actor_id(actor: Any) -> str | None:
    return str(actor.pk) if getattr(actor, "pk", None) else None

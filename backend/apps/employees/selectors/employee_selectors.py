"""Read-side employee queries. Every list/lookup is scope-filtered (``apps.employees.scope``).

Query budget (verified by tests): the list page is a constant number of queries regardless of page
size - persons are joined, the primary email/mobile are prefetched once per page, and sensitive
tables (identifiers, addresses, emergency contacts) are never touched by list queries.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from django.db.models import Exists, OuterRef, Prefetch, Q, QuerySet
from django.http import Http404

from .. import permissions
from ..models import (
    Address,
    Contact,
    ContactType,
    EmergencyContact,
    Employee,
    EmployeeIdentifier,
    TimelineEntry,
    normalize_identifier,
)
from ..scope import visible_employees
from ..validators import normalize_email, normalize_phone

PRIMARY_CONTACTS = Prefetch(
    "contacts",
    queryset=Contact.objects.filter(
        is_primary=True, contact_type__in=[ContactType.EMAIL, ContactType.MOBILE]
    ),
    to_attr="primary_contacts",
)


def get_employee_list(user: Any) -> QuerySet[Employee]:
    """Scoped employees with person joined and primary email/mobile prefetched (lists, API)."""
    qs = Employee.objects.select_related("person", "user").prefetch_related(PRIMARY_CONTACTS)
    return visible_employees(user, qs).order_by("code")


def search_employees(user: Any, queryset: QuerySet[Employee], term: str) -> QuerySet[Employee]:
    """Case-insensitive search on code, names, email and phone (permission-aware).

    National identifiers are matched **only** for holders of ``employees.view_identifiers`` and only
    as an exact normalized value - never a partial match that could be used to enumerate CNICs.
    """
    term = (term or "").strip()
    if not term:
        return queryset
    q: Any = (
        Q(code__icontains=term)
        | Q(person__first_name__icontains=term)
        | Q(person__last_name__icontains=term)
        | Q(person__preferred_name__icontains=term)
        | Q(person__middle_name__icontains=term)
    )
    parts = term.split()
    if len(parts) > 1:  # "Gulzar Ahmed" -> first AND last
        q |= Q(person__first_name__icontains=parts[0], person__last_name__icontains=parts[-1])
    if "@" in term:
        q |= Exists(
            Contact.objects.filter(employee=OuterRef("pk"), normalized_value=normalize_email(term))
        )
    digits = re.sub(r"\D", "", term)
    if len(digits) >= 4 and len(digits) >= len(term.replace(" ", "")) - 2:
        phone = normalize_phone(term).lstrip("+")
        q |= Exists(
            Contact.objects.filter(
                employee=OuterRef("pk"),
                contact_type__in=[ContactType.MOBILE, ContactType.PHONE],
                normalized_value__contains=phone[-10:],
            )
        )
        if permissions.can_view_identifiers(user):
            q |= Exists(
                EmployeeIdentifier.objects.filter(
                    employee=OuterRef("pk"), normalized_value=normalize_identifier(term)
                )
            )
    return queryset.filter(q)


def get_employee(user: Any, pk: Any) -> Employee:
    """Scoped lookup; out-of-scope ids raise Http404 exactly like missing ids (no oracle)."""
    try:
        uuid.UUID(str(pk))
    except ValueError as exc:
        raise Http404("Employee not found.") from exc
    employee = get_employee_list(user).filter(pk=pk).first()
    if employee is None:
        raise Http404("Employee not found.")
    return employee


def get_employee_detail(user: Any, pk: Any) -> Employee:
    """Employee with everything the detail page reads prefetched (sections are permission-gated in
    the view); keeps the page at a constant query count."""
    employee = get_employee(user, pk)
    return (
        Employee.objects.select_related("person", "user", "created_by", "updated_by")
        .prefetch_related("contacts", "addresses", "emergency_contacts", "identifiers")
        .get(pk=employee.pk)
    )


def get_employee_by_code(user: Any, code: str) -> Employee:
    qs = visible_employees(user, Employee.objects.select_related("person"))
    employee = qs.filter(code__iexact=code.strip()).first()
    if employee is None:
        raise Http404("Employee not found.")
    return employee


def get_employee_by_user(account: Any) -> Employee | None:
    """The employee linked to a login account (no scope: for "my own record" lookups)."""
    return Employee.objects.select_related("person").filter(user=account).first()


def get_employee_contacts(employee: Employee) -> QuerySet[Contact]:
    return employee.contacts.all().order_by("-is_primary", "contact_type", "created_at")


def get_employee_addresses(
    employee: Employee, *, include_history: bool = True
) -> QuerySet[Address]:
    qs = employee.addresses.all()
    if not include_history:
        qs = qs.filter(effective_to__isnull=True)
    return qs.order_by("address_type", "-is_primary", "-effective_from")


def get_employee_emergency_contacts(employee: Employee) -> QuerySet[EmergencyContact]:
    return employee.emergency_contacts.all().order_by("-is_primary", "name")


def get_employee_identifiers(employee: Employee) -> QuerySet[EmployeeIdentifier]:
    return employee.identifiers.select_related("verified_by").order_by(
        "-is_primary", "identifier_type"
    )


def get_employee_timeline(
    user: Any, employee: Employee, *, limit: int = 100
) -> list[TimelineEntry]:
    """Newest first; sensitive entries only for ``view_sensitive_identity`` holders."""
    qs = employee.timeline.select_related("actor").order_by("-occurred_at")
    if not permissions.can_view_sensitive_identity(user):
        qs = qs.filter(is_sensitive=False)
    return list(qs[:limit])

"""Which employees a user may see - the single scope decision for the employee domain.

Phase 3 has no organizational placement for employees (Assignment is Phase 4, ADR-020), so the rule
is deliberately conservative and **fails closed**:

* superusers and users holding the ``global`` organization scope see every employee;
* everybody else sees **no** employee records.

Phase 4 plugs organization-aware visibility in *without changing any caller* by registering a
resolver that maps the user's org scopes to employees through their current Assignment, e.g.::

    from apps.employees.scope import register_employee_scope_resolver
    from apps.organizations.services import OrganizationScopeService

    def by_assignment(user, qs):
        assignments = OrganizationScopeService.filter_queryset(
            user, Assignment.objects.current(), "restaurant", prefix="restaurant")
        return qs.filter(pk__in=assignments.values("employee_id"))

    register_employee_scope_resolver(by_assignment)

Selectors (lists, search, export), detail views, every service write and every API endpoint go
through :func:`visible_employees` / :func:`can_access_employee`, so scope is enforced server-side once.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.db.models import Q, QuerySet

from apps.accounts.services import ScopeService

Resolver = Callable[[Any, QuerySet], QuerySet]
_RESOLVERS: list[Resolver] = []


def register_employee_scope_resolver(resolver: Resolver) -> None:
    """Add a rule that returns the subset of ``qs`` the user may see (results are OR-ed)."""
    if resolver not in _RESOLVERS:
        _RESOLVERS.append(resolver)


def unregister_employee_scope_resolver(resolver: Resolver) -> None:
    if resolver in _RESOLVERS:
        _RESOLVERS.remove(resolver)


def _active(user: Any) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_active", False))


def has_full_access(user: Any) -> bool:
    return _active(user) and (user.is_superuser or ScopeService.has_global_scope(user))


def visible_employees(user: Any, queryset: QuerySet) -> QuerySet:
    """Restrict an Employee queryset (or any queryset with ``employee`` FK via ``employee_path``)."""
    if not _active(user):
        return queryset.none()
    if has_full_access(user):
        return queryset
    if not _RESOLVERS:
        return queryset.none()
    ids_q = Q()
    for resolver in _RESOLVERS:
        ids_q |= Q(pk__in=resolver(user, queryset.model._default_manager.all()).values("pk"))
    return queryset.filter(ids_q)


def can_access_employee(user: Any, employee: Any) -> bool:
    if employee is None or not _active(user):
        return False
    if has_full_access(user):
        return True
    return visible_employees(user, type(employee)._default_manager.filter(pk=employee.pk)).exists()


def can_access_person(user: Any, person: Any) -> bool:
    """A person is reachable through their employee record; a person *without* one (candidate,
    relative) is only reachable with organization-wide scope."""
    employee = getattr(person, "employee", None) if person is not None else None
    try:
        employee = person.employee  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 - reverse one-to-one raises when absent
        employee = None
    if employee is not None:
        return can_access_employee(user, employee)
    return has_full_access(user)

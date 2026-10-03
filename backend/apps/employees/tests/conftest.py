"""Fixtures for the employee domain tests.

The employee master record spans several tables, so most tests need "an employee that already exists
with one of everything". :func:`make_employee` builds exactly that, going through the real service
layer rather than ``Model.objects.create``, so the fixtures cannot drift away from the workflows the
services actually implement.
"""

from __future__ import annotations

import datetime as dt

import pytest

from apps.accounts.models import UserScope
from apps.employees import permissions as emp_perms
from apps.employees.models import Employee
from apps.employees.services import EmployeeService

TODAY = dt.date(2026, 10, 3)

#: Everything an HR administrator needs to work with an employee master record.
HR_ADMIN = sorted(emp_perms.HR_ADMIN_PERMS)

#: Enough to create and read employees, but not to see identifiers or change sensitive records.
HR_OFFICER = sorted(emp_perms.HR_OFFICER_PERMS)


@pytest.fixture
def make_employee(make_user):
    """Factory returning an ``Employee``, with counters so each call is a distinct person."""
    counter = {"n": 0}

    def _make(actor=None, *, status="active", **person_overrides):
        counter["n"] += 1
        person_data = {
            "first_name": f"Employee{counter['n']}",
            "last_name": "Tester",
            "date_of_birth": dt.date(1990, 1, counter["n"]),
            "gender": "prefer_not_to_say",
            "nationality": "PK",
            **person_overrides,
        }
        return EmployeeService.create_employee(
            actor=actor,
            person_data=person_data,
            status=status,
            contacts=[
                {
                    "contact_type": "mobile",
                    "value": f"+92 300 000{counter['n']:04d}",
                    "is_primary": True,
                },
                {
                    "contact_type": "email",
                    "value": f"employee{counter['n']}@example.com",
                    "is_primary": True,
                },
            ],
            identifiers=[
                {
                    "identifier_type": "cnic",
                    "value": f"42101-{counter['n']:07d}-3",
                    "is_primary": True,
                }
            ],
            addresses=[
                {
                    "address_type": "current",
                    "address_line_1": f"{counter['n']} Test Street",
                    "city": "Karachi",
                    "country": "PK",
                    "effective_from": dt.date(2024, 1, 1),
                }
            ],
            emergency_contacts=[
                {
                    "name": f"Contact{counter['n']}",
                    "relationship": "sibling",
                    "phone": f"0300-111{counter['n']:04d}",
                    "is_primary": True,
                }
            ],
        )

    return _make


@pytest.fixture
def hr_admin(make_user):
    """A user holding every employee-domain permission (not a superuser)."""
    user = make_user("hr-admin@example.com", perms=HR_ADMIN)
    UserScope.objects.create(user=user, scope_type="global", scope_ref="*")
    return user


@pytest.fixture
def hr_officer(make_user):
    """A user who may create/read employees but not see identifiers or archive."""
    user = make_user("hr-officer@example.com", perms=HR_OFFICER)
    UserScope.objects.create(user=user, scope_type="global", scope_ref="*")
    return user


@pytest.fixture
def employee(make_employee, hr_admin):
    """One fully populated employee, owned by the fixtures that need it."""
    return make_employee(actor=hr_admin)


@pytest.fixture
def employee_qs(employee):  # pragma: no cover - convenience for assertNumQueries-style tests
    return Employee.objects.all()

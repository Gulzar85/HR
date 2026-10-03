"""Data-quality checks and query-count / scale behaviour of the employee list."""

from __future__ import annotations

import datetime as dt

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.data_quality.registry import run_checks
from apps.employees.models import Contact, Employee, Person

pytestmark = pytest.mark.django_db


def codes() -> set[str]:
    return {i.check for i in run_checks("employees")}


def test_clean_data_has_no_errors(make_employee):
    make_employee()
    make_employee()
    assert not {c for c in codes() if "DUPLICATE" in c or "INVALID" in c or "MULTIPLE" in c}


def test_detects_duplicates_and_bad_records(make_employee):
    a = make_employee()
    b = make_employee(first_name=a.person.first_name, date_of_birth=a.person.date_of_birth)
    Contact.objects.filter(employee=b, contact_type="email").update(
        value=a.primary_email.value, normalized_value=a.primary_email.normalized_value
    )
    Contact.objects.filter(employee=b, contact_type="mobile").update(is_primary=False)
    Person.objects.filter(pk=b.person_id).update(
        date_of_birth=dt.date.today() + dt.timedelta(days=5)
    )
    found = codes()
    assert {"EMP-DUPLICATE-EMAIL", "EMP-INVALID-DOB"} <= found
    issue = next(i for i in run_checks("employees") if i.check == "EMP-DUPLICATE-EMAIL")
    assert a.primary_email.value not in issue.message  # findings never echo contact values


def test_list_query_count_is_constant(client, hr_admin, make_employee, settings):
    settings.EMS_ADMIN_PAGE_SIZE = 25
    client.force_login(hr_admin)
    make_employee(actor=hr_admin)
    with CaptureQueriesContext(connection) as small:
        client.get(reverse("employees:list"))
    for _ in range(15):
        make_employee(actor=hr_admin)
    with CaptureQueriesContext(connection) as big:
        client.get(reverse("employees:list"))
    assert len(big) <= len(small) + 1  # no N+1


@pytest.mark.slow
def test_ten_thousand_employees_search_and_paginate(client, hr_admin):
    people = Person.objects.bulk_create(
        Person(first_name=f"P{i}", last_name="Bulk") for i in range(10_000)
    )
    Employee.objects.bulk_create(
        Employee(person=p, code=f"EMP-{i + 100000:06d}") for i, p in enumerate(people)
    )
    client.force_login(hr_admin)
    with CaptureQueriesContext(connection) as q:
        r = client.get(reverse("employees:list"), {"q": "EMP-109999"})
    assert r.status_code == 200 and [e.code for e in r.context["employees"]] == ["EMP-109999"]
    assert len(q) < 30
    r = client.get(reverse("employees:list"), {"page": 200})
    assert r.status_code == 200 and r.context["page_obj"].paginator.count == 10_000

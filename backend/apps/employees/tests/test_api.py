"""Employee REST API: CRUD, masking/reveal, sensitive omission, scope, pagination, errors."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserScope
from apps.audit.models import AuditLog
from apps.employees import permissions as P
from apps.employees.models import Employee

from .conftest import HR_ADMIN

pytestmark = pytest.mark.django_db
URL = "/api/v1/employees/"


def api(user) -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return c


@pytest.fixture
def viewer(make_user):
    user = make_user("apiviewer@example.com", perms=[P.VIEW])
    UserScope.objects.create(user=user, scope_type="global", scope_ref="*")
    return user


def test_auth_required_and_permissions(make_user, employee):
    assert APIClient().get(URL).status_code == 401
    assert api(make_user("none@example.com")).get(URL).status_code == 403


def test_list_is_minimal_and_paginated(hr_admin, make_employee, employee):
    for _ in range(3):
        make_employee(actor=hr_admin)
    r = api(hr_admin).get(URL, {"page_size": 2})
    assert r.status_code == 200 and r.data["count"] == 4 and len(r.data["results"]) == 2
    row = r.data["results"][0]
    assert set(row) == {
        "id",
        "code",
        "employee_status",
        "person",
        "email",
        "mobile",
        "has_user_account",
        "created_at",
    }
    assert "date_of_birth" not in row["person"]


def test_search_and_filter(hr_admin, make_employee, employee):
    other = make_employee(actor=hr_admin)
    client = api(hr_admin)
    assert [x["code"] for x in client.get(URL, {"q": other.code}).data["results"]] == [other.code]
    client.post(
        f"{URL}{other.pk}/status/",
        {"employee_status": "inactive", "reason": "leave"},
        format="json",
    )
    assert [
        x["code"] for x in client.get(URL, {"employee_status": "inactive"}).data["results"]
    ] == [other.code]


def test_detail_for_admin_masks_identifiers(hr_admin, employee):
    data = api(hr_admin).get(f"{URL}{employee.pk}/").data["data"]
    ident = employee.identifiers.first()
    assert (
        data["identifiers"][0]["value"] == ident.masked_value and data["identifiers"][0]["masked"]
    )
    assert data["person"]["date_of_birth"] and data["addresses"] and data["emergency_contacts"]


def test_detail_omits_sensitive_sections_for_viewer(viewer, employee):
    data = api(viewer).get(f"{URL}{employee.pk}/").data["data"]
    for key in ("identifiers", "addresses", "emergency_contacts", "user"):
        assert key not in data
    assert "date_of_birth" not in data["person"] and "gender" not in data["person"]
    assert employee.identifiers.first().value not in str(data)
    client = api(viewer)
    for path in ("identifiers/", "addresses/", "emergency-contacts/", "timeline/"):
        assert client.get(f"{URL}{employee.pk}/{path}").status_code == 403, path


def test_reveal_requires_both_perms_and_is_audited(hr_admin, hr_officer, employee):
    ident = employee.identifiers.first()
    r = api(hr_admin).get(f"{URL}{employee.pk}/identifiers/", {"reveal": "1"})
    assert r.data["data"][0]["value"] == ident.value and not r.data["data"][0]["masked"]
    assert AuditLog.objects.filter(
        object_id=str(employee.pk), action="employees.identifier_viewed"
    ).exists()
    assert (
        api(hr_officer).get(f"{URL}{employee.pk}/identifiers/", {"reveal": "1"}).status_code == 403
    )


def test_out_of_scope_and_unknown_are_404(make_user, employee):
    unscoped = make_user("apiunscoped@example.com", perms=HR_ADMIN)
    client = api(unscoped)
    assert client.get(URL).data["count"] == 0
    assert client.get(f"{URL}{employee.pk}/").status_code == 404
    assert (
        client.patch(f"{URL}{employee.pk}/", {"first_name": "Hacked"}, format="json").status_code
        == 404
    )
    assert client.get(f"{URL}00000000-0000-0000-0000-000000000000/").status_code in (403, 404)
    employee.person.refresh_from_db()
    assert employee.person.first_name != "Hacked"


def test_create_with_duplicate_conflict(hr_admin, employee):
    body = {
        "person": {"first_name": "Ali", "last_name": "Raza"},
        "contacts": [
            {"contact_type": "email", "value": employee.primary_email.value, "is_primary": True}
        ],
    }
    client = api(hr_admin)
    r = client.post(URL, body, format="json")
    assert r.status_code == 409 and r.data["error"]["code"] == "possible_duplicate"
    r = client.post(URL, {**body, "confirm_duplicates": True}, format="json")
    assert r.status_code == 201 and r.data["data"]["code"].startswith("EMP-")


def test_create_validation_error(hr_admin):
    r = api(hr_admin).post(URL, {"person": {"first_name": "X"}}, format="json")
    assert r.status_code == 400


def test_patch_sensitive_field_requires_permission(hr_officer, hr_admin, employee):
    r = api(hr_officer).patch(
        f"{URL}{employee.pk}/", {"date_of_birth": "1970-01-01"}, format="json"
    )
    assert r.status_code == 403
    r = api(hr_admin).patch(f"{URL}{employee.pk}/", {"preferred_name": "Ali"}, format="json")
    assert r.status_code == 200 and r.data["data"]["person"]["preferred_name"] == "Ali"


def test_archive_requires_archive_permission(hr_officer, hr_admin, employee):
    url = f"{URL}{employee.pk}/status/"
    assert (
        api(hr_officer)
        .post(url, {"employee_status": "archived", "reason": "x"}, format="json")
        .status_code
        == 403
    )
    assert (
        api(hr_admin)
        .post(url, {"employee_status": "archived", "reason": "x"}, format="json")
        .status_code
        == 200
    )
    assert Employee.objects.get(pk=employee.pk).is_archived
    assert (
        api(hr_admin)
        .post(url, {"employee_status": "active", "reason": "back"}, format="json")
        .status_code
        == 200
    )


def test_child_endpoints_and_idor(hr_admin, make_employee, employee):
    client = api(hr_admin)
    r = client.post(
        f"{URL}{employee.pk}/contacts/",
        {"contact_type": "phone", "value": "042 35761234"},
        format="json",
    )
    assert r.status_code == 201
    other = make_employee(actor=hr_admin)
    foreign = other.contacts.first()
    assert client.delete(f"{URL}{employee.pk}/contacts/{foreign.pk}/").status_code == 404
    assert other.contacts.filter(pk=foreign.pk).exists()
    ident = employee.identifiers.first()
    r = client.post(
        f"{URL}{employee.pk}/identifiers/{ident.pk}/verification/",
        {"verification_status": "verified"},
        format="json",
    )
    assert r.status_code == 200 and r.data["data"]["verification_status"] == "verified"


def test_link_user(hr_admin, employee, make_user):
    make_user("linked@example.com")
    client = api(hr_admin)
    assert (
        client.post(
            f"{URL}{employee.pk}/user-link/", {"email": "linked@example.com"}, format="json"
        ).status_code
        == 200
    )
    assert Employee.objects.get(pk=employee.pk).user.email == "linked@example.com"
    assert (
        client.post(
            f"{URL}{employee.pk}/user-link/", {"email": "missing@example.com"}, format="json"
        ).status_code
        == 400
    )
    assert client.delete(f"{URL}{employee.pk}/user-link/").status_code == 200


def test_unmapped_methods_denied(hr_admin, employee):
    assert api(hr_admin).delete(f"{URL}{employee.pk}/").status_code in (403, 405)

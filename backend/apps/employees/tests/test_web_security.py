"""Employee UI + security: scope/IDOR, sensitive data exposure, HTMX bypass, photos, export."""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.accounts.models import UserScope
from apps.audit.models import AuditLog
from apps.employees import permissions as P
from apps.employees.models import Employee, EmployeeStatus

from .conftest import HR_ADMIN

pytestmark = pytest.mark.django_db


def png_bytes(size=(8, 8)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def unscoped_admin(make_user):
    """All employee permissions but NO organization scope."""
    return make_user("unscoped@example.com", perms=HR_ADMIN)


@pytest.fixture
def viewer(make_user):
    """Can see employees (global scope) but none of the sensitive data."""
    user = make_user("viewer@example.com", perms=[P.VIEW])
    UserScope.objects.create(user=user, scope_type="global", scope_ref="*")
    return user


# ------------------------------------------------------------------------- pages render
def test_all_pages_render_for_hr_admin(client, hr_admin, employee):
    client.force_login(hr_admin)
    urls = [
        reverse("employees:list"), reverse("employees:create"),
        reverse("employees:detail", args=[employee.pk]), reverse("employees:edit", args=[employee.pk]),
        reverse("employees:status", args=[employee.pk]), reverse("employees:link_user", args=[employee.pk]),
        reverse("employees:timeline", args=[employee.pk]),
        reverse("employees:contact_add", args=[employee.pk]), reverse("employees:address_add", args=[employee.pk]),
        reverse("employees:emergency_add", args=[employee.pk]), reverse("employees:identifier_add", args=[employee.pk]),
        reverse("employees:note_add", args=[employee.pk]),
    ]  # fmt: skip
    for url in urls:
        r = client.get(url)
        assert r.status_code == 200, url
        assert "#DA291C" not in r.content.decode().split("</style>", 1)[-1], url


def test_detail_shows_sections_and_masks_identifiers(client, hr_admin, employee):
    client.force_login(hr_admin)
    body = client.get(reverse("employees:detail", args=[employee.pk])).content.decode()
    identifier = employee.identifiers.first()
    assert identifier.masked_value in body and identifier.value not in body  # masked until revealed
    for section in (
        "sec-identity",
        "sec-contacts",
        "sec-addresses",
        "sec-emergency",
        "sec-identifiers",
        "sec-timeline",
    ):
        assert section in body


# ----------------------------------------------------------------------- authorization
def test_anonymous_and_unprivileged(client, employee, make_user):
    assert client.get(reverse("employees:list")).status_code == 302
    client.force_login(make_user("nobody@example.com"))
    assert client.get(reverse("employees:list")).status_code == 403
    assert client.get(reverse("employees:detail", args=[employee.pk])).status_code == 403


def test_scope_is_enforced_lists_and_idor(client, unscoped_admin, employee):
    client.force_login(unscoped_admin)
    r = client.get(reverse("employees:list"))
    assert r.status_code == 200 and r.context["page_obj"].paginator.count == 0
    for name in ("detail", "edit", "status", "timeline", "contact_add"):
        assert client.get(reverse(f"employees:{name}", args=[employee.pk])).status_code == 404, name
    r = client.post(
        reverse("employees:contact_add", args=[employee.pk]),
        {"contact_type": "mobile", "value": "+92 300 9999999"},
    )
    assert r.status_code == 404
    assert not employee.contacts.filter(value="+92 300 9999999").exists()


def test_viewer_sees_no_sensitive_data(client, viewer, employee):
    client.force_login(viewer)
    body = client.get(reverse("employees:detail", args=[employee.pk])).content.decode()
    ident = employee.identifiers.first()
    address = employee.addresses.first()
    emergency = employee.emergency_contacts.first()
    assert ident.value not in body and ident.masked_value not in body
    assert address.address_line_1 not in body
    assert emergency.name not in body and emergency.phone not in body
    assert "Restricted" in body  # identity details hidden
    assert employee.person.date_of_birth.strftime("%d %b %Y") not in body
    assert client.get(reverse("employees:photo", args=[employee.pk])).status_code == 403


def test_list_never_contains_sensitive_data(client, hr_admin, employee):
    client.force_login(hr_admin)
    body = client.get(reverse("employees:list")).content.decode()
    ident = employee.identifiers.first()
    assert ident.value not in body and ident.masked_value not in body
    assert employee.addresses.first().address_line_1 not in body


def test_htmx_and_direct_posts_are_authorized(client, viewer, employee):
    client.force_login(viewer)
    cases = [
        ("employees:contact_add", {"contact_type": "mobile", "value": "+92 300 1112223"}),
        ("employees:address_add", {"address_type": "current", "address_line_1": "x", "city": "y"}),
        ("employees:identifier_add", {"identifier_type": "passport", "value": "AB1234567"}),
        ("employees:note_add", {"content": "x", "visibility": "internal"}),
        ("employees:identifiers_reveal", {}),
    ]
    for name, data in cases:
        r = client.post(reverse(name, args=[employee.pk]), data, HTTP_HX_REQUEST="true")
        assert r.status_code == 403, name
    r = client.post(
        reverse("employees:status", args=[employee.pk]),
        {"employee_status": "archived", "reason": "x"},
    )
    employee.refresh_from_db()
    assert employee.employee_status == EmployeeStatus.ACTIVE
    assert (
        client.post(
            reverse("employees:link_user", args=[employee.pk]), {"email": viewer.email}
        ).status_code
        == 403
    )


def test_officer_cannot_archive_or_see_identifiers(client, hr_officer, employee):
    client.force_login(hr_officer)
    r = client.get(reverse("employees:status", args=[employee.pk]))
    assert "archived" not in [c for c, _ in r.context["form"].fields["employee_status"].choices]
    r = client.post(
        reverse("employees:status", args=[employee.pk]),
        {"employee_status": "archived", "reason": "x"},
    )
    assert r.status_code == 200  # invalid choice for this user
    employee.refresh_from_db()
    assert not employee.is_archived
    assert (
        "sec-identifiers"
        not in client.get(reverse("employees:detail", args=[employee.pk])).content.decode()
    )


def test_child_record_idor_across_employees(client, hr_admin, make_employee, employee):
    other = make_employee(actor=hr_admin)
    foreign_contact = other.contacts.first()
    client.force_login(hr_admin)
    r = client.post(reverse("employees:contact_remove", args=[employee.pk, foreign_contact.pk]))
    assert r.status_code == 404
    assert other.contacts.filter(pk=foreign_contact.pk).exists()


# ------------------------------------------------------------------------- workflows
def test_create_employee_through_ui_with_duplicate_warning(client, hr_admin, employee):
    client.force_login(hr_admin)
    email = employee.primary_email.value
    data = {
        "person-first_name": "Sara", "person-last_name": "Iqbal", "contacts-email": email,
        "contacts-mobile": "+92 301 5551234", "address-address_line_1": "", "emergency-name": "",
    }  # fmt: skip
    r = client.post(reverse("employees:create"), data)
    assert r.status_code == 200 and r.context["duplicates"]  # warned, not created
    assert not Employee.objects.filter(person__first_name="Sara").exists()
    r = client.post(reverse("employees:create"), {**data, "dup-confirm_duplicates": "on"})
    assert r.status_code == 302
    emp = Employee.objects.get(person__first_name="Sara")
    assert emp.code.startswith("EMP-") and emp.primary_mobile.value == "+92 301 5551234"


def test_create_partial_section_requires_its_fields(client, hr_admin):
    client.force_login(hr_admin)
    r = client.post(
        reverse("employees:create"),
        {"person-first_name": "A", "person-last_name": "B", "address-city": "Lahore"},
    )
    assert r.status_code == 200 and "Required when an address is entered" in r.content.decode()


def test_htmx_add_contact_returns_section(client, hr_admin, employee):
    client.force_login(hr_admin)
    r = client.post(
        reverse("employees:contact_add", args=[employee.pk]),
        {"contact_type": "phone", "value": "042 35761234", "label": "office"}, HTTP_HX_REQUEST="true",
    )  # fmt: skip
    body = r.content.decode()
    assert r.status_code == 200 and 'id="sec-contacts"' in body and "042 35761234" in body
    bad = client.post(
        reverse("employees:contact_add", args=[employee.pk]),
        {"contact_type": "phone", "value": "12"},
        HTTP_HX_REQUEST="true",
    )
    assert bad["HX-Retarget"] == "#sec-contacts-form" and "error" in bad.content.decode()


def test_reveal_identifiers_is_audited(client, hr_admin, employee):
    client.force_login(hr_admin)
    r = client.post(
        reverse("employees:identifiers_reveal", args=[employee.pk]), HTTP_HX_REQUEST="true"
    )
    assert employee.identifiers.first().value in r.content.decode()
    row = AuditLog.objects.get(action="employees.identifier_viewed", object_id=str(employee.pk))
    assert employee.identifiers.first().value not in str(row.changes)


def test_edit_sensitive_fields_gated(client, hr_officer, hr_admin, employee):
    client.force_login(hr_officer)
    r = client.get(reverse("employees:edit", args=[employee.pk]))
    assert "date_of_birth" not in r.context["form"].fields
    client.post(
        reverse("employees:edit", args=[employee.pk]),
        {"first_name": "Changed", "last_name": "Name", "date_of_birth": "1970-01-01"},
    )
    employee.person.refresh_from_db()
    assert (
        employee.person.first_name == "Changed"
        and str(employee.person.date_of_birth) != "1970-01-01"
    )


def test_photo_upload_serve_and_remove(client, hr_admin, employee):
    client.force_login(hr_admin)
    url = reverse("employees:edit", args=[employee.pk])
    base = {"first_name": employee.person.first_name, "last_name": employee.person.last_name}
    r = client.post(
        url,
        {
            **base,
            "photo-profile_photo": SimpleUploadedFile(
                "me.png", png_bytes(), content_type="image/png"
            ),
        },
    )
    assert r.status_code == 302
    employee.person.refresh_from_db()
    assert employee.person.profile_photo
    served = client.get(reverse("employees:photo", args=[employee.pk]))
    assert (
        served.status_code == 200
        and served["Content-Type"] == "image/png"
        and "private" in served["Cache-Control"]
    )
    r = client.post(url, {**base, "photo-remove_photo": "on"})
    employee.person.refresh_from_db()
    assert not employee.person.profile_photo


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("evil.png", b"<?php system($_GET['x']); ?>"),
        ("logo.svg", b"<svg onload=alert(1)></svg>"),
        ("run.exe", b"MZ\x90\x00"),
    ],
)
def test_bad_photo_uploads_rejected(client, hr_admin, employee, name, content):
    client.force_login(hr_admin)
    r = client.post(
        reverse("employees:edit", args=[employee.pk]),
        {
            "first_name": "X",
            "last_name": "Y",
            "photo-profile_photo": SimpleUploadedFile(name, content),
        },
    )
    assert r.status_code == 200
    employee.person.refresh_from_db()
    assert not employee.person.profile_photo


def test_link_and_unlink_user(client, hr_admin, employee, make_user):
    account = make_user("staffer@example.com")
    client.force_login(hr_admin)
    client.post(
        reverse("employees:link_user", args=[employee.pk]), {"email": "staffer@example.com"}
    )
    employee.refresh_from_db()
    assert employee.user == account
    client.post(reverse("employees:unlink_user", args=[employee.pk]))
    employee.refresh_from_db()
    assert employee.user is None
    account.refresh_from_db()
    assert account.is_active  # the account itself is untouched


def test_archive_and_restore_via_ui(client, hr_admin, employee):
    client.force_login(hr_admin)
    client.post(
        reverse("employees:status", args=[employee.pk]),
        {"employee_status": "archived", "reason": "left"},
    )
    employee.refresh_from_db()
    assert employee.is_archived
    client.post(
        reverse("employees:status", args=[employee.pk]),
        {"employee_status": "active", "reason": "rehired"},
    )
    employee.refresh_from_db()
    assert employee.is_active


def test_search_filters_and_pagination(client, hr_admin, make_employee, settings):
    settings.EMS_ADMIN_PAGE_SIZE = 3
    emps = [make_employee(actor=hr_admin) for _ in range(5)]
    client.force_login(hr_admin)
    url = reverse("employees:list")
    r = client.get(url)
    assert len(r.context["employees"]) == 3 and r.context["page_obj"].paginator.count == 5
    target = emps[2]
    for term in (
        target.code,
        target.code.lower(),
        target.person.first_name.upper(),
        target.primary_email.value.upper(),
        target.primary_mobile.value[-7:],
    ):
        codes = [e.code for e in client.get(url, {"q": term}).context["employees"]]
        assert target.code in codes, term
    cnic = target.identifiers.first().value
    assert [e.code for e in client.get(url, {"q": cnic}).context["employees"]] == [
        target.code
    ]  # admin may match exact CNIC
    assert client.get(url, {"has_user": "false"}).context["page_obj"].paginator.count == 5
    partial = client.get(url, {"q": "Employee"}, HTTP_HX_REQUEST="true").content.decode()
    assert "<html" not in partial and "<table" in partial


def test_officer_search_cannot_match_identifiers(client, hr_officer, hr_admin, make_employee):
    target = make_employee(actor=hr_admin)
    client.force_login(hr_officer)
    r = client.get(reverse("employees:list"), {"q": target.identifiers.first().value})
    assert target.code not in [e.code for e in r.context["employees"]]
    assert "gender" not in r.context["filter"].form.fields  # sensitive filters removed


def test_export_requires_permission_excludes_sensitive_and_is_audited(
    client, hr_admin, hr_officer, employee
):
    client.force_login(hr_officer)
    assert client.get(reverse("employees:export")).status_code == 403
    client.force_login(hr_admin)
    r = client.get(reverse("employees:export"))
    body = b"".join(r.streaming_content).decode()
    assert r.status_code == 200 and employee.code in body
    assert (
        employee.identifiers.first().value not in body
        and employee.addresses.first().address_line_1 not in body
    )
    assert AuditLog.objects.filter(action="employees.employee_exported", actor=hr_admin).exists()

"""Authorization-bypass, IDOR, CSRF and privilege-escalation tests against the real HTTP layer."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.accounts.models import AccountEvent, Role, UserRole, UserSession, UserStatus

pytestmark = pytest.mark.django_db

ADMIN_GET_URLS = [
    "accounts:user_list",
    "accounts:user_create",
    "accounts:role_list",
    "accounts:role_create",
    "accounts:group_list",
    "accounts:group_create",
]


@pytest.mark.parametrize("name", ADMIN_GET_URLS)
def test_anonymous_is_redirected_to_login(client, name):
    r = client.get(reverse(name))
    assert r.status_code == 302 and r.url.startswith("/accounts/login/")


@pytest.mark.parametrize("name", ADMIN_GET_URLS)
def test_authenticated_without_permission_gets_403(client, normal_user, name):
    client.force_login(normal_user)
    assert client.get(reverse(name)).status_code == 403


def test_admin_can_use_admin_pages(client, admin_user, make_user):
    target = make_user("target@example.com")
    client.force_login(admin_user)
    for url in [
        reverse("accounts:user_list"),
        reverse("accounts:user_create"),
        reverse("accounts:user_detail", args=[target.pk]),
        reverse("accounts:user_edit", args=[target.pk]),
        reverse("accounts:user_roles", args=[target.pk]),
        reverse("accounts:user_groups", args=[target.pk]),
        reverse("accounts:user_scopes", args=[target.pk]),
        reverse("accounts:user_set_password", args=[target.pk]),
        reverse("accounts:user_security", args=[target.pk]),
        reverse("accounts:role_list"),
        reverse("accounts:role_create"),
        reverse("accounts:group_list"),
        reverse("accounts:group_create"),
        reverse("accounts:profile"),
        reverse("accounts:sessions"),
        reverse("home"),
    ]:
        r = client.get(url)
        assert r.status_code == 200, url
        assert "Traceback" not in r.content.decode()


def test_direct_post_without_permission_changes_nothing(client, normal_user, make_user):
    victim = make_user("victim@example.com")
    client.force_login(normal_user)
    r = client.post(reverse("accounts:user_status", args=[victim.pk]), {"action": "deactivate"})
    assert r.status_code == 403
    victim.refresh_from_db()
    assert victim.status == UserStatus.ACTIVE
    assert (
        client.post(
            reverse("accounts:user_set_password", args=[victim.pk]), {"password": "x"}
        ).status_code
        == 403
    )
    assert (
        client.post(reverse("accounts:user_roles", args=[victim.pk]), {"roles": []}).status_code
        == 403
    )
    assert (
        client.post(reverse("accounts:role_create"), {"name": "x", "code": "x"}).status_code == 403
    )
    assert not Role.objects.filter(code="x").exists()


def test_view_only_user_cannot_mutate(client, make_user):
    viewer = make_user(perms=["accounts.view_user", "accounts.view_role"])
    victim = make_user("v2@example.com")
    client.force_login(viewer)
    assert client.get(reverse("accounts:user_detail", args=[victim.pk])).status_code == 200
    r = client.get(reverse("accounts:user_detail", args=[victim.pk]))
    assert "Suspend" not in r.content.decode()  # UI hint only...
    assert (
        client.post(
            reverse("accounts:user_status", args=[victim.pk]), {"action": "suspend"}
        ).status_code
        == 403
    )  # ...backend decides
    assert client.get(reverse("accounts:user_security", args=[victim.pk])).status_code == 403


def test_status_view_is_post_only(client, admin_user, make_user):
    victim = make_user()
    client.force_login(admin_user)
    assert client.get(reverse("accounts:user_status", args=[victim.pk])).status_code == 405


def test_admin_post_actions_require_csrf(admin_user, make_user):
    victim = make_user()
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(admin_user)
    r = strict.post(reverse("accounts:user_status", args=[victim.pk]), {"action": "suspend"})
    assert r.status_code == 403
    victim.refresh_from_db()
    assert victim.status == UserStatus.ACTIVE


def test_idor_unknown_uuid_is_404_not_a_leak(client, admin_user):
    client.force_login(admin_user)
    ghost = uuid.uuid4()
    for name in ("user_detail", "user_edit", "user_security", "user_roles"):
        assert client.get(reverse(f"accounts:{name}", args=[ghost])).status_code == 404
    assert client.get(reverse("accounts:role_detail", args=[ghost])).status_code == 404


def test_idor_user_cannot_revoke_someone_elses_session(client, make_user, password):
    a, b = make_user("a@example.com"), make_user("b@example.com")
    cb = Client()
    cb.force_login(b)
    b_session = UserSession.objects.get(user=b)
    client.force_login(a)
    r = client.post(reverse("accounts:session_revoke", args=[b_session.pk]))
    assert r.status_code == 302
    b_session.refresh_from_db()
    assert b_session.revoked_at is None and cb.get("/profile/").status_code == 200  # B untouched


def test_user_can_revoke_own_other_session(client, make_user, password):
    a = make_user("self@example.com")
    other_device = Client()
    other_device.force_login(a)
    client.force_login(a)
    target = UserSession.objects.exclude(session_key=client.session.session_key).get(user=a)
    client.post(reverse("accounts:session_revoke", args=[target.pk]))
    assert other_device.get("/profile/").status_code == 302
    assert client.get("/profile/").status_code == 200
    assert AccountEvent.objects.filter(user=a, event_type="session_revoked").exists()


def test_session_page_never_leaks_session_keys(client, make_user):
    a = make_user("keys@example.com")
    client.force_login(a)
    key = client.session.session_key
    assert key not in client.get(reverse("accounts:sessions")).content.decode()


def test_privilege_escalation_via_role_assignment_is_blocked(client, make_user):
    delegate = make_user(perms=["accounts.manage_users", "accounts.view_user"])
    god = Role.objects.create(name="God", code="god")
    god.permissions.add(Permission.objects.get(codename="manage_permissions"))
    victim = make_user("lowly@example.com")
    client.force_login(delegate)
    r = client.post(reverse("accounts:user_roles", args=[victim.pk]), {"roles": [god.pk]})
    assert r.status_code == 403  # cannot hand out permissions it does not hold
    assert not UserRole.objects.filter(user=victim).exists()


def test_user_cannot_grant_self_privileges_via_profile(client, normal_user):
    client.force_login(normal_user)
    r = client.post(
        reverse("accounts:profile"),
        {"first_name": "N", "last_name": "U", "email": "normal@example.com", "theme_mode": "dark",
         "is_superuser": "on", "is_staff": "on", "status": "active", "roles": "x"},
    )  # fmt: skip
    assert r.status_code == 302
    normal_user.refresh_from_db()
    assert not normal_user.is_superuser and not normal_user.is_staff
    assert normal_user.roles.count() == 0
    assert normal_user.preferences == {"theme_mode": "dark"}


def test_admin_cannot_deactivate_self_through_ui(client, admin_user):
    client.force_login(admin_user)
    client.post(reverse("accounts:user_status", args=[admin_user.pk]), {"action": "deactivate"})
    admin_user.refresh_from_db()
    assert admin_user.status == UserStatus.ACTIVE


def test_non_superuser_cannot_touch_superuser_account(client, admin_user, make_user):
    root = make_user("root@example.com", superuser=True)
    client.force_login(admin_user)
    r = client.post(reverse("accounts:user_status", args=[root.pk]), {"action": "suspend"})
    assert r.status_code == 403
    r = client.post(
        reverse("accounts:user_set_password", args=[root.pk]),
        {"password": "x", "confirm_password": "x"},
    )
    assert r.status_code == 403
    root.refresh_from_db()
    assert root.status == UserStatus.ACTIVE


def test_deactivated_users_session_stops_working(client, admin_user, make_user):
    target = make_user("gone@example.com")
    victim_browser = Client()
    victim_browser.force_login(target)
    assert victim_browser.get("/profile/").status_code == 200
    client.force_login(admin_user)
    client.post(reverse("accounts:user_status", args=[target.pk]), {"action": "deactivate"})
    assert victim_browser.get("/profile/").status_code == 302


def test_suspended_session_is_rejected_even_if_session_survived(make_user):
    """Defence in depth: even without session deletion, a non-active user is never authenticated."""
    from django.contrib.sessions.models import Session

    target = make_user("susp@example.com")
    browser = Client()
    browser.force_login(target)
    target.status = UserStatus.SUSPENDED
    target.save()  # bypasses the service: sessions are NOT revoked
    assert Session.objects.count() == 1
    assert browser.get("/profile/").status_code == 302


def test_user_list_filters_search_and_pagination(client, admin_user, make_user, settings):
    settings.EMS_ADMIN_PAGE_SIZE = 5
    for i in range(12):
        make_user(f"person{i}@example.com", first_name=f"Person{i}")
    make_user("suspended.one@example.com", status="suspended")
    client.force_login(admin_user)
    page1 = client.get(reverse("accounts:user_list"))
    assert page1.status_code == 200 and len(page1.context["users"]) == 5
    assert page1.context["page_obj"].paginator.count == 14
    r = client.get(reverse("accounts:user_list"), {"status": "suspended"})
    assert [u.email for u in r.context["users"]] == ["suspended.one@example.com"]
    r = client.get(reverse("accounts:user_list"), {"q": "person11"})
    assert [u.email for u in r.context["users"]] == ["person11@example.com"]
    htmx = client.get(reverse("accounts:user_list"), {"q": "person1"}, HTTP_HX_REQUEST="true")
    body = htmx.content.decode()
    assert "<html" not in body and "<table" in body  # partial for HTMX
    assert "HX-Request" in htmx.headers["Vary"]


def test_user_list_has_no_n_plus_one(client, admin_user, make_user, django_assert_max_num_queries):
    role = Role.objects.create(name="R", code="r")
    for i in range(30):
        u = make_user(f"bulk{i}@example.com")
        UserRole.objects.create(user=u, role=role)
    client.force_login(admin_user)
    with django_assert_max_num_queries(14):
        assert client.get(reverse("accounts:user_list")).status_code == 200


def test_filter_by_role_and_group(client, admin_user, make_user):
    from django.contrib.auth.models import Group

    role = Role.objects.create(name="Finder", code="finder")
    a, b = make_user("a1@example.com"), make_user("b1@example.com")
    UserRole.objects.create(user=a, role=role)
    g = Group.objects.create(name="Grp")
    b.groups.add(g)
    client.force_login(admin_user)
    r = client.get(reverse("accounts:user_list"), {"role": role.pk})
    assert [u.email for u in r.context["users"]] == ["a1@example.com"]
    r = client.get(reverse("accounts:user_list"), {"group": g.pk})
    assert [u.email for u in r.context["users"]] == ["b1@example.com"]


def test_end_to_end_user_administration_via_ui(
    client, admin_user, django_capture_on_commit_callbacks, mailoutbox
):
    client.force_login(admin_user)
    role = Role.objects.create(name="Clerk", code="clerk")
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post(
            reverse("accounts:user_create"),
            {"email": "new@example.com", "first_name": "N", "last_name": "P", "roles": [role.pk]},
        )
    assert r.status_code == 302
    from apps.accounts.models import User

    user = User.objects.get(email="new@example.com")
    assert user.status == UserStatus.PENDING and user.roles.filter(pk=role.pk).exists()
    assert len(mailoutbox) == 1
    client.post(
        reverse("accounts:user_status", args=[user.pk]),
        {"action": "activate", "reason": "verified"},
    )
    user.refresh_from_db()
    assert user.status == UserStatus.ACTIVE
    client.post(reverse("accounts:user_edit", args=[user.pk]),
                {"email": "new@example.com", "first_name": "Renamed", "last_name": "P", "username": user.username})  # fmt: skip
    user.refresh_from_db()
    assert user.first_name == "Renamed"
    page = client.get(reverse("accounts:user_security", args=[user.pk])).content.decode()
    assert "Account status changed" in page and "User created" in page


def test_role_and_group_administration_via_ui(client, admin_user, make_user):
    client.force_login(admin_user)
    r = client.post(
        reverse("accounts:role_create"), {"name": "Ops", "code": "ops", "description": "d"}
    )
    role = Role.objects.get(code="ops")
    assert r.url == reverse("accounts:role_permissions", args=[role.pk])
    view_user = Permission.objects.get(codename="view_user", content_type__app_label="accounts")
    client.post(
        reverse("accounts:role_permissions", args=[role.pk]), {"permissions": [view_user.pk]}
    )
    assert list(role.permissions.all()) == [view_user]
    assert client.get(reverse("accounts:role_detail", args=[role.pk])).status_code == 200
    client.post(reverse("accounts:role_toggle", args=[role.pk]))
    role.refresh_from_db()
    assert not role.is_active

    client.post(reverse("accounts:group_create"), {"name": "Team A", "description": ""})
    from apps.accounts.models import GroupProfile

    profile = GroupProfile.objects.get(group__name="Team A")
    member = make_user("member@example.com")
    client.post(
        reverse("accounts:group_member_add", args=[profile.pk]), {"email": "member@example.com"}
    )
    assert member.groups.filter(pk=profile.group_id).exists()
    client.post(reverse("accounts:group_member_remove", args=[profile.pk, member.pk]))
    assert not member.groups.exists()
    assert client.get(reverse("accounts:group_detail", args=[profile.pk])).status_code == 200


def test_permission_matrix_rejects_unknown_permission_ids(client, admin_user):
    role = Role.objects.create(name="Matrix", code="matrix")
    client.force_login(admin_user)
    r = client.post(
        reverse("accounts:role_permissions", args=[role.pk]), {"permissions": ["999999"]}
    )
    assert r.status_code == 200 and not role.permissions.exists()  # validation error, nothing saved


def test_profile_theme_preference_changes_rendered_theme(client, normal_user):
    client.force_login(normal_user)
    client.post(
        reverse("accounts:profile"),
        {"first_name": "N", "last_name": "U", "email": normal_user.email, "theme_mode": "dark"},
    )
    css = client.get(reverse("accounts:profile")).content.decode()
    assert "color-scheme: dark" in css
    client.post(
        reverse("accounts:profile"),
        {"first_name": "N", "last_name": "U", "email": normal_user.email, "theme_mode": "light"},
    )
    assert "color-scheme: light;" in client.get(reverse("accounts:profile")).content.decode()


def test_profile_email_conflict_is_a_form_error(client, make_user):
    make_user("taken@example.com")
    me = make_user("me@example.com")
    client.force_login(me)
    r = client.post(
        reverse("accounts:profile"),
        {"first_name": "M", "last_name": "E", "email": "taken@example.com", "theme_mode": "system"},
    )
    assert r.status_code == 200 and "already exists" in r.content.decode()
    me.refresh_from_db()
    assert me.email == "me@example.com"


def test_django_admin_requires_staff(client, normal_user, make_user):
    client.force_login(normal_user)
    assert client.get("/django-admin/").status_code == 302  # redirected to admin login: not staff
    staff = make_user("staffer@example.com", superuser=True)
    client.force_login(staff)
    assert client.get("/django-admin/").status_code == 200
    assert client.get("/django-admin/accounts/loginevent/").status_code == 200
    assert client.get("/django-admin/accounts/loginevent/add/").status_code == 403  # read-only

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import LoginEvent, Role, UserSession, UserStatus

pytestmark = pytest.mark.django_db

V1 = "/api/v1"


def api(token=None) -> APIClient:
    c = APIClient()
    if token:
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


def obtain(email, password):
    r = APIClient().post(f"{V1}/auth/token/", {"email": email, "password": password}, format="json")
    assert r.status_code == 200, r.content
    return r.json()["data"]


def test_token_obtain_and_me(make_user, password):
    user = make_user("api@example.com", perms=["accounts.view_user"])
    tokens = obtain("API@example.com", password)
    assert (
        set(tokens) >= {"access", "refresh", "token_type", "expires_in"}
        and tokens["token_type"] == "Bearer"
    )
    r = api(tokens["access"]).get(f"{V1}/auth/me/")
    assert r.status_code == 200
    me = r.json()["data"]
    assert me["email"] == "api@example.com" and "accounts.view_user" in me["permissions"]
    assert "password" not in me and "refresh" not in str(me)
    assert LoginEvent.objects.filter(user=user, channel="api", event_type="login_success").exists()


def test_invalid_credentials_use_error_envelope(make_user):
    make_user("bad@example.com")
    r = APIClient().post(
        f"{V1}/auth/token/", {"email": "bad@example.com", "password": "nope"}, format="json"
    )
    assert r.status_code == 401
    assert r.json() == {
        "error": {"code": "invalid_credentials", "message": "Invalid credentials.", "details": {}}
    }
    assert (
        LoginEvent.objects.filter(event_type="login_failed", channel="web").exists()
        or LoginEvent.objects.filter(event_type="login_failed").exists()
    )


@pytest.mark.parametrize("status", ["suspended", "inactive", "pending", "locked"])
def test_non_active_accounts_cannot_get_tokens(make_user, password, status):
    make_user("s@example.com", status=status)
    r = APIClient().post(
        f"{V1}/auth/token/", {"email": "s@example.com", "password": password}, format="json"
    )
    assert r.status_code == 401


def test_api_lockout_policy_applies(make_user, password, settings):
    settings.EMS_MAX_FAILED_LOGINS = 2
    user = make_user("lockapi@example.com")
    for _ in range(2):
        APIClient().post(
            f"{V1}/auth/token/", {"email": "lockapi@example.com", "password": "x"}, format="json"
        )
    user.refresh_from_db()
    assert user.status == UserStatus.LOCKED
    assert obtain_status("lockapi@example.com", password) == 401


def obtain_status(email, password):
    return (
        APIClient()
        .post(f"{V1}/auth/token/", {"email": email, "password": password}, format="json")
        .status_code
    )


def test_login_endpoint_is_throttled(make_user):
    make_user("thr@example.com")
    codes = [obtain_status("thr@example.com", "wrong") for _ in range(12)]
    assert 429 in codes


def test_missing_and_malformed_tokens_are_rejected_consistently():
    assert APIClient().get(f"{V1}/auth/me/").status_code == 401
    assert api("not-a-jwt").get(f"{V1}/auth/me/").status_code == 401
    r = api("a.b.c").get(f"{V1}/users/")
    assert r.status_code == 401 and "error" in r.json() and "code" in r.json()["error"]


def test_expired_access_token_is_rejected(make_user):
    user = make_user("exp@example.com")
    token = AccessToken.for_user(user)
    token.set_exp(lifetime=-timedelta(seconds=5))
    r = api(str(token)).get(f"{V1}/auth/me/")
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_not_valid"


def test_token_signed_with_wrong_key_is_rejected(make_user):
    import jwt

    user = make_user("forged@example.com")
    forged = jwt.encode(
        {"user_id": str(user.pk), "token_type": "access", "exp": 9999999999, "jti": "x"},
        "wrong-key" * 4,
        "HS256",
    )
    assert api(forged).get(f"{V1}/auth/me/").status_code == 401


def test_refresh_rotates_and_old_token_is_revoked(make_user, password):
    make_user("rot@example.com")
    first = obtain("rot@example.com", password)
    r = APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": first["refresh"]}, format="json")
    assert r.status_code == 200
    second = r.json()["data"]
    assert second["refresh"] != first["refresh"]
    replay = APIClient().post(
        f"{V1}/auth/token/refresh/", {"refresh": first["refresh"]}, format="json"
    )
    assert replay.status_code == 401  # single-use
    assert api(second["access"]).get(f"{V1}/auth/me/").status_code == 200


def test_access_token_is_not_accepted_as_refresh(make_user, password):
    make_user("mix@example.com")
    tokens = obtain("mix@example.com", password)
    r = APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": tokens["access"]}, format="json")
    assert r.status_code == 401


def test_logout_blacklists_refresh_token(make_user, password):
    make_user("lo@example.com")
    tokens = obtain("lo@example.com", password)
    assert (
        APIClient()
        .post(f"{V1}/auth/logout/", {"refresh": tokens["refresh"]}, format="json")
        .status_code
        == 200
    )
    r = APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert r.status_code == 401
    assert LoginEvent.objects.filter(event_type="logout", channel="api").exists()


def test_deactivating_user_revokes_api_access(make_user, admin_user, password):
    from apps.accounts.services import UserService

    target = make_user("kill@example.com")
    tokens = obtain("kill@example.com", password)
    assert api(tokens["access"]).get(f"{V1}/auth/me/").status_code == 200
    UserService.deactivate(target, actor=admin_user)
    assert (
        api(tokens["access"]).get(f"{V1}/auth/me/").status_code == 401
    )  # access token dies at once
    r = APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert r.status_code == 401  # refresh token blacklisted


def test_api_password_change_revokes_refresh_tokens(make_user, password):
    make_user("pc@example.com")
    tokens = obtain("pc@example.com", password)
    c = api(tokens["access"])
    bad = c.post(
        f"{V1}/auth/password/change/",
        {"old_password": "no", "new_password": "N3w-Very-Str0ng!pw"},
        format="json",
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "validation_error"
    ok = c.post(
        f"{V1}/auth/password/change/",
        {"old_password": password, "new_password": "N3w-Very-Str0ng!pw"},
        format="json",
    )
    assert ok.status_code == 200
    assert (
        APIClient()
        .post(f"{V1}/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
        .status_code
        == 401
    )
    assert obtain_status("pc@example.com", "N3w-Very-Str0ng!pw") == 200


# ------------------------------------------------------------------------ authorization
def tok(user) -> str:
    return str(RefreshToken.for_user(user).access_token)


def test_users_endpoint_requires_permission_server_side(normal_user, admin_user):
    assert APIClient().get(f"{V1}/users/").status_code == 401
    r = api(tok(normal_user)).get(f"{V1}/users/")
    assert r.status_code == 403 and r.json()["error"]["code"] == "permission_denied"
    assert api(tok(admin_user)).get(f"{V1}/users/").status_code == 200


def test_unmapped_methods_fail_closed(admin_user, make_user):
    target = make_user("t@example.com")
    c = api(tok(admin_user))
    assert c.delete(f"{V1}/users/{target.pk}/").status_code in (403, 405)
    assert c.put(f"{V1}/roles/", {}, format="json").status_code in (403, 405)


def test_user_list_pagination_filter_and_no_secrets(admin_user, make_user):
    for i in range(30):
        make_user(f"p{i}@example.com")
    make_user("sus@example.com", status="suspended")
    c = api(tok(admin_user))
    r = c.get(f"{V1}/users/", {"page_size": 10})
    body = r.json()
    assert body["count"] == 32 and len(body["results"]) == 10 and body["next"]
    assert "password" not in str(body) and "session" not in str(body).lower()
    r = c.get(f"{V1}/users/", {"status": "suspended"})
    assert [u["email"] for u in r.json()["results"]] == ["sus@example.com"]
    assert c.get(f"{V1}/users/", {"q": "p17"}).json()["count"] == 1


def test_create_update_and_status_via_api(
    admin_user, django_capture_on_commit_callbacks, mailoutbox
):
    c = api(tok(admin_user))
    role = Role.objects.create(name="API Role", code="api-role")
    with django_capture_on_commit_callbacks(execute=True):
        r = c.post(
            f"{V1}/users/",
            {"email": "created@example.com", "first_name": "C", "role_ids": [str(role.pk)]},
            format="json",
        )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["status"] == "pending" and data["roles"] == ["api-role"] and len(mailoutbox) == 1
    dup = c.post(f"{V1}/users/", {"email": "CREATED@example.com"}, format="json")
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_email"

    uid = data["id"]
    assert (
        c.patch(f"{V1}/users/{uid}/", {"first_name": "Changed"}, format="json").json()["data"][
            "first_name"
        ]
        == "Changed"
    )
    r = c.post(f"{V1}/users/{uid}/status/", {"action": "activate", "reason": "ok"}, format="json")
    assert r.status_code == 200 and r.json()["data"]["status"] == "active"
    r = c.post(f"{V1}/users/{uid}/status/", {"action": "activate"}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_status_transition"
    assert (
        c.post(f"{V1}/users/{uid}/status/", {"action": "lock"}, format="json").status_code == 400
    )  # system-only


def test_api_user_creation_cannot_escalate(make_user):
    delegate = make_user(perms=["accounts.add_user", "accounts.manage_users", "accounts.view_user"])
    strong = Role.objects.create(name="Strong", code="strong")
    strong.permissions.add(Permission.objects.get(codename="manage_permissions"))
    r = api(tok(delegate)).post(
        f"{V1}/users/", {"email": "esc@example.com", "role_ids": [str(strong.pk)]}, format="json"
    )
    assert r.status_code == 403
    from apps.accounts.models import User

    assert not User.objects.filter(email="esc@example.com").exists()  # atomic: nothing was created


def test_status_endpoint_blocked_without_manage_users(make_user):
    viewer = make_user(perms=["accounts.view_user", "accounts.change_user"])
    target = make_user()
    r = api(tok(viewer)).post(
        f"{V1}/users/{target.pk}/status/", {"action": "suspend"}, format="json"
    )
    assert r.status_code == 403
    target.refresh_from_db()
    assert target.status == UserStatus.ACTIVE


def test_roles_and_permissions_endpoints(admin_user, make_user):
    c = api(tok(admin_user))
    r = c.post(
        f"{V1}/roles/", {"name": "Via API", "permissions": ["accounts.view_user"]}, format="json"
    )
    assert r.status_code == 201 and r.json()["data"]["permissions"] == ["accounts.view_user"]
    rid = r.json()["data"]["id"]
    r = c.patch(f"{V1}/roles/{rid}/", {"permissions": []}, format="json")
    assert r.json()["data"]["permissions"] == []
    assert (
        c.post(
            f"{V1}/roles/", {"name": "Bad", "permissions": ["nope.nothing"]}, format="json"
        ).status_code
        == 400
    )
    listing = c.get(f"{V1}/permissions/").json()["results"]
    assert any(p["label"] == "accounts.manage_users" for p in listing)
    assert not any(p["label"].startswith(("sessions.", "contenttypes.", "admin.")) for p in listing)
    # roles without manage_roles cannot be created
    plain = make_user(perms=["accounts.view_role"])
    assert api(tok(plain)).post(f"{V1}/roles/", {"name": "X"}, format="json").status_code == 403
    assert api(tok(plain)).get(f"{V1}/roles/").status_code == 200


def test_api_sessions_are_own_only_and_hide_keys(make_user):
    from django.test import Client

    a, b = make_user("sa@example.com"), make_user("sb@example.com")
    for u in (a, b):
        Client().force_login(u)
    mine = api(tok(a)).get(f"{V1}/sessions/").json()["results"]
    assert len(mine) == 1 and set(mine[0]) == {"id", "created_at", "ip_address", "user_agent"}
    foreign = UserSession.objects.get(user=b)
    assert api(tok(a)).delete(f"{V1}/sessions/{foreign.pk}/").status_code == 404  # IDOR
    assert api(tok(a)).delete(f"{V1}/sessions/{mine[0]['id']}/").status_code == 200
    assert api(tok(a)).get(f"{V1}/sessions/").json()["results"] == []


def test_api_is_versioned_and_unversioned_path_does_not_exist():
    assert APIClient().get("/api/users/").status_code == 404
    assert APIClient().get("/api/v1/").status_code == 200

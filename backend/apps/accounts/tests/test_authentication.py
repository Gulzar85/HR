from __future__ import annotations

import re

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import LoginEvent, User, UserSession, UserStatus

pytestmark = pytest.mark.django_db
LOGIN = "/accounts/login/"


def _login(client, email, password, **extra):
    return client.post(LOGIN, {"username": email, "password": password, **extra})


def test_login_page_renders_with_theme_tokens(client):
    r = client.get(LOGIN)
    assert r.status_code == 200
    body = r.content.decode()
    assert "--color-primary" in body and "Sign in" in body
    assert "#DA291C" not in body.split("</style>", 1)[1]
    assert 'type="email"' in body and 'for="id_username"' in body  # labelled, accessible
    nonce = re.search(r'<style nonce="([^"]+)"', body).group(1)  # non-empty
    assert f"'nonce-{nonce}'" in r.headers["Content-Security-Policy"]  # inline theme CSS is allowed


def test_valid_login_records_event_and_session(client, make_user, password):
    user = make_user("ok@example.com")
    r = _login(client, "OK@example.com", password)  # email is case-insensitive
    assert r.status_code == 302 and r.url == "/"
    assert client.get("/profile/").status_code == 200
    assert (
        LoginEvent.objects.filter(user=user, event_type="login_success", success=True).count() == 1
    )
    assert UserSession.objects.filter(user=user, revoked_at__isnull=True).count() == 1
    user.refresh_from_db()
    assert user.last_login is not None


def test_invalid_login_is_generic_and_recorded(client, make_user, password):
    make_user("who@example.com")
    for email, pw in [("who@example.com", "wrong"), ("ghost@example.com", password)]:
        r = _login(client, email, pw)
        assert r.status_code == 200
        assert "incorrect, or the account is unavailable" in r.content.decode()
    reasons = set(
        LoginEvent.objects.filter(event_type="login_failed").values_list(
            "failure_reason", flat=True
        )
    )
    assert reasons == {"bad_credentials", "unknown_user"}


def test_status_cannot_sign_in_and_message_is_identical(client, make_user, password):
    for status in ("suspended", "inactive", "pending"):
        make_user(f"{status}@example.com", status=status)
        r = _login(client, f"{status}@example.com", password)
        assert (
            r.status_code == 200
            and "incorrect, or the account is unavailable" in r.content.decode()
        )
        assert "_auth_user_id" not in client.session
    assert LoginEvent.objects.filter(failure_reason="account_suspended").exists()


def test_account_locks_after_repeated_failures(client, make_user, password, settings):
    settings.EMS_MAX_FAILED_LOGINS = 3
    user = make_user("brute@example.com")
    for _ in range(3):
        _login(client, "brute@example.com", "nope")
    user.refresh_from_db()
    assert user.status == UserStatus.LOCKED and user.locked_until
    assert LoginEvent.objects.filter(user=user, event_type="account_locked").exists()
    # the correct password no longer works while locked
    r = _login(client, "brute@example.com", password)
    assert r.status_code == 200 and "_auth_user_id" not in client.session


def test_success_resets_failure_counter(client, make_user, password):
    user = make_user("reset@example.com")
    _login(client, "reset@example.com", "bad")
    user.refresh_from_db()
    assert user.failed_login_count == 1
    _login(client, "reset@example.com", password)
    user.refresh_from_db()
    assert user.failed_login_count == 0


def test_remember_me_controls_session_expiry(client, make_user, password, settings):
    make_user("rm@example.com")
    _login(client, "rm@example.com", password)
    assert client.session.get_expire_at_browser_close()
    c2 = Client()
    _login(c2, "rm@example.com", password, remember_me="on")
    assert not c2.session.get_expire_at_browser_close()
    assert c2.session.get_expiry_age() == settings.EMS_REMEMBER_ME_SECONDS


def test_logout_requires_post_and_records_event(client, make_user, password):
    user = make_user("out@example.com")
    _login(client, "out@example.com", password)
    assert client.get("/accounts/logout/").status_code == 405  # no logout-by-link (CSRF-able)
    r = client.post("/accounts/logout/")
    assert r.status_code == 302
    assert client.get("/profile/").status_code == 302
    assert LoginEvent.objects.filter(user=user, event_type="logout").exists()
    assert UserSession.objects.get(user=user).revoked_at is not None


def test_login_is_csrf_protected(make_user, password):
    make_user("csrf@example.com")
    strict = Client(enforce_csrf_checks=True)
    assert (
        strict.post(LOGIN, {"username": "csrf@example.com", "password": password}).status_code
        == 403
    )


def test_password_change_flow(client, make_user, password):
    user = make_user("chg@example.com")
    other = Client()
    _login(other, "chg@example.com", password)
    _login(client, "chg@example.com", password)

    r = client.post(
        "/accounts/password/change/",
        {
            "old_password": "wrong",
            "new_password": "Br4nd-New-Pass#1",
            "confirm_password": "Br4nd-New-Pass#1",
        },
    )
    assert r.status_code == 200 and "incorrect" in r.content.decode().lower()

    r = client.post(
        "/accounts/password/change/",
        {
            "old_password": password,
            "new_password": "Br4nd-New-Pass#1",
            "confirm_password": "Br4nd-New-Pass#1",
        },
    )
    assert r.status_code == 302
    user.refresh_from_db()
    assert user.check_password("Br4nd-New-Pass#1")
    assert client.get("/profile/").status_code == 200  # current session survives
    assert other.get("/profile/").status_code == 302  # other devices signed out
    assert LoginEvent.objects.filter(user=user, event_type="password_changed").exists()
    assert UserSession.objects.filter(user=user, revoked_at__isnull=True).count() == 1


def test_password_change_enforces_validators(client, make_user, password):
    make_user("val@example.com")
    _login(client, "val@example.com", password)
    r = client.post(
        "/accounts/password/change/",
        {"old_password": password, "new_password": "password1", "confirm_password": "password1"},
    )
    assert r.status_code == 200 and "common" in r.content.decode().lower()


def test_password_reset_end_to_end(
    client, make_user, password, mailoutbox, django_capture_on_commit_callbacks
):
    user = make_user("fp@example.com")
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post("/accounts/password/reset/", {"email": "fp@example.com"})
    assert r.status_code == 302
    assert len(mailoutbox) == 1
    link = re.search(r"https?://\S+/accounts/password/reset/\S+/\S+/", mailoutbox[0].body).group(0)
    path = link.split("testserver", 1)[1]

    follow = client.get(path, follow=True)  # Django swaps the token into the session
    assert follow.status_code == 200
    r = client.post(
        follow.request["PATH_INFO"],
        {"new_password1": "Fresh-Pass-w0rd!7", "new_password2": "Fresh-Pass-w0rd!7"},
    )
    assert r.status_code == 302
    user.refresh_from_db()
    assert user.check_password("Fresh-Pass-w0rd!7")
    assert LoginEvent.objects.filter(user=user, event_type="password_reset_requested").exists()
    assert LoginEvent.objects.filter(user=user, event_type="password_reset_completed").exists()

    # token is single-use
    again = Client().get(path, follow=True)
    assert "Link not valid" in again.content.decode()
    # tokens never reach the event tables
    assert not any(
        "reset" in (e.identifier or "") and "/" in (e.identifier or "")
        for e in LoginEvent.objects.all()
    )


def test_password_reset_does_not_enumerate_accounts(
    client, make_user, mailoutbox, django_capture_on_commit_callbacks
):
    make_user("real@example.com")
    with django_capture_on_commit_callbacks(execute=True):
        known = client.post("/accounts/password/reset/", {"email": "real@example.com"})
        unknown = client.post("/accounts/password/reset/", {"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 302
    assert known.url == unknown.url
    assert len(mailoutbox) == 1


def test_inactive_account_gets_no_reset_email(
    client, make_user, mailoutbox, django_capture_on_commit_callbacks
):
    make_user("gone@example.com", status="inactive")
    with django_capture_on_commit_callbacks(execute=True):
        client.post("/accounts/password/reset/", {"email": "gone@example.com"})
    assert mailoutbox == []


def test_invitation_acceptance_activates_pending_user(
    client, make_user, admin_user, mailoutbox, django_capture_on_commit_callbacks, settings
):
    from apps.accounts.services import UserService

    settings.EMS_SITE_URL = (
        "http://testserver"  # services without a request need a configured site URL
    )

    with django_capture_on_commit_callbacks(execute=True):
        user = UserService.create_user(actor=admin_user, email="newhire@example.com")
    link = re.search(r"https?://\S+/accounts/password/reset/\S+/\S+/", mailoutbox[0].body).group(0)
    path = link.split("testserver", 1)[1]
    follow = client.get(path, follow=True)
    client.post(
        follow.request["PATH_INFO"],
        {"new_password1": "Welc0me-Aboard!9", "new_password2": "Welc0me-Aboard!9"},
    )
    user.refresh_from_db()
    assert user.status == UserStatus.ACTIVE
    assert reverse("accounts:login")
    assert _login(Client(), "newhire@example.com", "Welc0me-Aboard!9").status_code == 302


def test_credentials_never_stored_in_login_events(client, make_user, password):
    make_user("secret@example.com")
    _login(client, "secret@example.com", "My-Typed-Secret-1")
    _login(client, "secret@example.com", password)
    blob = str(list(LoginEvent.objects.values()))
    assert "My-Typed-Secret-1" not in blob and password not in blob
    assert User.objects.get(email="secret@example.com").password not in blob

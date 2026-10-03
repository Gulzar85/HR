from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import authenticate
from django.utils import timezone

from apps.accounts.models import AccountEvent, LoginEvent, User, UserStatus
from apps.accounts.services import UserService
from apps.audit.models import AuditLog
from apps.common.exceptions import (
    BusinessRuleException,
    ConflictException,
    PermissionDeniedException,
    ValidationException,
)
from apps.outbox.models import OutboxEvent

pytestmark = pytest.mark.django_db


def test_create_user_normalizes_email_hashes_password(admin_user, password):
    user = UserService.create_user(
        actor=admin_user, email="  New.Person@Example.COM ", first_name="New", password=password
    )
    assert user.email == "new.person@example.com"
    assert user.pk.version == 4
    assert user.password != password and "$" in user.password  # salted hash, never plaintext
    assert user.check_password(password)
    assert user.status == UserStatus.ACTIVE and user.is_active
    assert user.username == "newperson"  # generated handle, never a login identifier


def test_user_has_no_employee_or_org_fields():
    names = {f.name for f in User._meta.concrete_fields}  # reverse accessors are not columns
    assert not names & {
        "employee",
        "employee_id",
        "designation",
        "department",
        "restaurant",
        "region",
        "manager",
    }


def test_duplicate_email_is_rejected_case_insensitively(admin_user, password):
    UserService.create_user(actor=admin_user, email="dup@example.com", password=password)
    with pytest.raises(ConflictException):
        UserService.create_user(actor=admin_user, email="DUP@example.com", password=password)


def test_weak_password_rejected(admin_user):
    with pytest.raises(ValidationException):
        UserService.create_user(actor=admin_user, email="weak@example.com", password="12345678")
    assert not User.objects.filter(email="weak@example.com").exists()


def test_create_without_password_is_pending_and_sends_invite(
    admin_user, django_capture_on_commit_callbacks, mailoutbox
):
    with django_capture_on_commit_callbacks(execute=True):
        user = UserService.create_user(actor=admin_user, email="invitee@example.com")
    assert user.status == UserStatus.PENDING and not user.is_active
    assert not user.has_usable_password()
    assert len(mailoutbox) == 1 and "activate" in mailoutbox[0].subject.lower()
    assert "/accounts/password/reset/" in mailoutbox[0].body


def test_create_user_requires_permission(normal_user):
    with pytest.raises(PermissionDeniedException):
        UserService.create_user(
            actor=normal_user, email="x@example.com", password="Str0ng-Passw0rd!x"
        )


def test_create_user_is_atomic_with_roles(admin_user, password):
    from apps.accounts.models import Role

    inactive = Role.objects.create(name="Dead", code="dead", is_active=False)
    with pytest.raises(BusinessRuleException):
        UserService.create_user(
            actor=admin_user, email="atomic@example.com", password=password, roles=[inactive]
        )
    assert not User.objects.filter(email="atomic@example.com").exists()  # rolled back


def test_status_transitions_and_audit(admin_user, make_user):
    target = make_user("t@example.com")
    UserService.suspend(target, actor=admin_user, reason="investigation")
    target.refresh_from_db()
    assert target.status == UserStatus.SUSPENDED and not target.is_active
    assert authenticate(username="t@example.com", password="Str0ng-Passw0rd!x") is None  # suspended

    UserService.activate(target, actor=admin_user)
    target.refresh_from_db()
    assert target.is_active
    UserService.deactivate(target, actor=admin_user, reason="left company")
    target.refresh_from_db()
    assert target.status == UserStatus.INACTIVE
    assert authenticate(username="t@example.com", password="Str0ng-Passw0rd!x") is None  # inactive

    events = AccountEvent.objects.filter(user=target, event_type="status_changed")
    assert events.count() == 3
    assert events.filter(reason="investigation", actor=admin_user).exists()
    assert (
        AuditLog.objects.filter(action="accounts.status_changed", object_id=str(target.pk)).count()
        == 3
    )
    assert LoginEvent.objects.filter(user=target, event_type="account_deactivated").exists()
    assert OutboxEvent.objects.filter(event_type="accounts.user_deactivated").exists()


def test_invalid_transition_rejected(admin_user, make_user):
    target = make_user("v@example.com")
    with pytest.raises(BusinessRuleException):
        UserService.unlock(target, actor=admin_user)  # not locked
    with pytest.raises(BusinessRuleException):
        UserService.activate(target, actor=admin_user)  # already active


def test_cannot_suspend_or_deactivate_self(admin_user):
    with pytest.raises(PermissionDeniedException):
        UserService.deactivate(admin_user, actor=admin_user)
    with pytest.raises(PermissionDeniedException):
        UserService.suspend(admin_user, actor=admin_user)


def test_only_superuser_manages_superuser(admin_user, make_user):
    root = make_user("root@example.com", superuser=True)
    with pytest.raises(PermissionDeniedException):
        UserService.suspend(root, actor=admin_user)
    other_super = make_user("root2@example.com", superuser=True)
    UserService.suspend(root, actor=other_super)  # allowed (and audited)
    assert AccountEvent.objects.filter(user=root, actor=other_super).exists()


def test_deactivation_ends_sessions(admin_user, make_user, client):
    from django.contrib.sessions.models import Session

    target = make_user("s@example.com")
    client.force_login(target)
    assert Session.objects.count() == 1
    UserService.deactivate(target, actor=admin_user)
    assert Session.objects.count() == 0
    assert client.get("/profile/").status_code == 302  # no longer authenticated


def test_lockout_expires_automatically(make_user, password):
    user = make_user("lock@example.com")
    UserService.lock(user, until=timezone.now() - timedelta(seconds=1))
    user.refresh_from_db()
    assert user.status == UserStatus.LOCKED
    assert authenticate(username="lock@example.com", password=password) is not None  # auto-unlock
    user.refresh_from_db()
    assert user.status == UserStatus.ACTIVE
    assert LoginEvent.objects.filter(user=user, event_type="account_unlocked").exists()


def test_update_user_records_before_after(admin_user, make_user):
    target = make_user("u@example.com", first_name="Old")
    UserService.update_user(actor=admin_user, user=target, first_name="New")
    event = AccountEvent.objects.get(user=target, event_type="user_updated")
    assert event.before == {"first_name": "Old"} and event.after == {"first_name": "New"}


def test_set_password_by_admin_revokes_sessions_and_never_logs_it(admin_user, make_user, client):
    from django.contrib.sessions.models import Session

    target = make_user("pw@example.com")
    client.force_login(target)
    UserService.set_password_by_admin(
        actor=admin_user, user=target, password="An0ther-Str0ng-Pass!"
    )
    assert Session.objects.count() == 0
    dump = str(list(AuditLog.objects.values())) + str(list(AccountEvent.objects.values()))
    assert "An0ther-Str0ng-Pass!" not in dump

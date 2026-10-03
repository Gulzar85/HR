"""Shared fixtures. Tests run against the settings in config.settings.testing."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission
from django.core.cache import cache

PASSWORD = "Str0ng-Passw0rd!x"

ALL_ACCOUNT_PERMS = [
    "accounts.view_user", "accounts.add_user", "accounts.change_user", "accounts.view_role",
    "accounts.manage_users", "accounts.manage_roles", "accounts.manage_permissions",
    "accounts.view_security_history", "audit.view_audit_logs",
]  # fmt: skip


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # throttling counters live in the cache
    yield
    cache.clear()


@pytest.fixture
def password() -> str:
    return PASSWORD


@pytest.fixture
def make_user(db):
    from apps.accounts.models import Role, User, UserRole

    counter = {"n": 0}

    def _make(
        email=None, *, perms=(), password=PASSWORD, status="active", superuser=False, **extra
    ):
        counter["n"] += 1
        email = email or f"user{counter['n']}@example.com"
        user = User.objects.create_user(
            username=email.split("@")[0] + str(counter["n"]),
            email=email,
            password=password,
            **extra,
        )
        if superuser:
            user.is_superuser = user.is_staff = True
        user.status = status
        user.save()
        if perms:
            role = Role.objects.create(name=f"Role {counter['n']}", code=f"role-{counter['n']}")
            for label in perms:
                app, codename = label.split(".")
                role.permissions.add(
                    Permission.objects.get(content_type__app_label=app, codename=codename)
                )
            UserRole.objects.create(user=user, role=role)
        return user

    return _make


@pytest.fixture
def admin_user(make_user):
    """A human administrator with every identity permission (not a superuser)."""
    return make_user("admin@example.com", perms=ALL_ACCOUNT_PERMS)


@pytest.fixture
def normal_user(make_user):
    return make_user("normal@example.com")


@pytest.fixture
def login(client):
    def _login(user):
        client.force_login(user)
        return client

    return _login

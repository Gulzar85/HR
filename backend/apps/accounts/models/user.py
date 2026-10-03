"""System user. A User is NOT an Employee (docs/adr/ADR-002, ADR-008).

Identity/account data only: no employee id, designation, department, restaurant, region, manager
or salary. The Employee domain (Phase 3) will hold a nullable link *to* User, never the reverse.

Login identifier policy: **email** (unique, stored lower-case). ``username`` is a unique handle
kept for Django compatibility and service accounts; it is never a second login identifier.

``is_staff`` = may open the Django admin fallback UI. ``is_superuser`` = bypasses permission
checks (still audited). Neither replaces roles/permissions/scopes.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


class UserStatus(models.TextChoices):
    PENDING = "pending", "Pending activation"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    LOCKED = "locked", "Locked"
    INACTIVE = "inactive", "Inactive"


class UserManager(DjangoUserManager["User"]):
    def _create_user_object(self, username, email, password, **extra_fields):
        # Phase 0 relied on Django's helper signature; keep it, but normalise + require email.
        if not email:
            raise ValueError("An email address is required.")
        return super()._create_user_object(  # type: ignore[misc]
            username, self.normalize_email(email), password, **extra_fields
        )

    def get_by_email(self, email: str) -> User:
        return self.get(email__iexact=email.strip())

    def create_superuser(self, username=None, email=None, password=None, **extra_fields):
        extra_fields.setdefault("status", UserStatus.ACTIVE)
        return super().create_superuser(username or email, email, password, **extra_fields)


class User(TimeStampedModel, AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email address", unique=True)

    status = models.CharField(
        max_length=12, choices=UserStatus.choices, default=UserStatus.ACTIVE, db_index=True
    )
    status_reason = models.CharField(max_length=255, blank=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)

    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    roles = models.ManyToManyField(
        "accounts.Role",
        through="accounts.UserRole",
        through_fields=("user", "role"),
        related_name="users",
    )
    preferences = models.JSONField(default=dict, blank=True)  # UI preferences only, validated

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()  # type: ignore[misc]

    class Meta:
        db_table = "accounts_user"
        permissions = [
            ("manage_users", "Can manage users (lifecycle, roles, groups, scopes, sessions)"),
            ("manage_roles", "Can manage roles and groups"),
            ("manage_permissions", "Can change permissions assigned to roles and groups"),
            ("view_security_history", "Can view user security history"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[s.value for s in UserStatus]),
                name="user_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["last_login"], name="user_last_login_idx"),
            models.Index(fields=["date_joined"], name="user_date_joined_idx"),
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        # ``is_active`` is derived: only ACTIVE accounts can authenticate. Status is the source of truth.
        self.is_active = self.status == UserStatus.ACTIVE
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "status" in update_fields:
            kwargs["update_fields"] = {*update_fields, "is_active"}
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.email

    @property
    def is_locked_out(self) -> bool:
        return self.status == UserStatus.LOCKED and bool(
            self.locked_until and self.locked_until > timezone.now()
        )

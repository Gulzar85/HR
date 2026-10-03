"""System user. A User is NOT an Employee (see docs/adr/ADR-002).

There is deliberately no foreign key to any employee model here. Later phases link the two
from the employee side (e.g. ``Employee.user`` nullable one-to-one) so that system users can
exist without being employees and employees may have no login.
Future organization/restaurant/manager *scope* is modelled by permissions + scope grants in
Phase 1, not by columns on this table.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models.functions import Lower


class UserManager(DjangoUserManager):
    def create_user(self, username, email=None, password=None, **extra):
        if email:
            email = self.normalize_email(email)
        return super().create_user(username, email, password, **extra)

    def get_by_login(self, identifier: str) -> User:
        """Look up by username or (case-insensitive) email."""
        field = "email__iexact" if "@" in identifier else "username__iexact"
        return self.get(**{field: identifier})  # type: ignore[return-value]


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email address", blank=True)  # type: ignore[misc]

    objects = UserManager()  # type: ignore[misc]

    class Meta:
        db_table = "accounts_user"
        constraints = [
            # Case-insensitive uniqueness for non-empty emails.
            models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="uniq_user_email_ci",
            )
        ]

    def __str__(self) -> str:
        return self.get_username()

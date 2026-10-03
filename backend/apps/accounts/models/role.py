"""Roles and group profiles.

* **Permission** - Django's ``auth.Permission`` (``app.action_model``): a business capability.
* **Role** - a named, administrator-managed *set of permissions* assigned to users.
* **Group** - Django ``auth.Group`` (+ ``GroupProfile``): a *collection of users* (team, committee)
  that may also carry permissions. Groups answer "who", roles answer "what job function".
* **Scope** - see ``user_scope.py``: *where* (which part of the organization) permissions apply.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db import models
from django.db.models.functions import Lower

from apps.common.models import TimeStampedModel


class Role(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    code = models.SlugField(
        max_length=60, unique=True, help_text="Stable machine name, e.g. hr-administrator"
    )
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_system = models.BooleanField(default=False, help_text="Seeded role; cannot be deleted.")
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="uniq_role_name_ci")]

    def __str__(self) -> str:
        return self.name


class UserRole(models.Model):
    """User <-> Role assignment, with who/when for traceability."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_roles"
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="uniq_user_role")]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.role_id}"


class GroupProfile(TimeStampedModel):
    """Adds UUID addressing, description and active flag to Django's Group (no second group system)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="profile")
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["group__name"]

    def __str__(self) -> str:
        return self.group.name

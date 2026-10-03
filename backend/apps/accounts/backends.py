"""Authentication/permission backend.

* Login identifier is the (case-insensitive) email.
* Lockouts expire automatically.
* Permissions = direct + **active groups** + **active roles** (``Role.permissions``). Object-level
  permissions are handled by django-guardian's backend (listed after this one).
"""

from __future__ import annotations

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.utils import timezone


class IdentityBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        from .models import User, UserStatus

        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is not None:
            username = username.strip().lower()
            locked = User.objects.filter(
                email=username, status=UserStatus.LOCKED, locked_until__lte=timezone.now()
            ).first()
            if locked is not None:
                from .services.user_service import UserService

                UserService.unlock(locked, actor=None, reason="lockout_expired")
        return super().authenticate(request, username=username, password=password, **kwargs)

    def _get_group_permissions(self, user_obj):
        """Despite the Django name this returns *all indirect* permissions: groups and roles."""
        return Permission.objects.filter(
            Q(group__in=user_obj.groups.filter(profile__is_active=True))
            | Q(roles__in=user_obj.roles.filter(is_active=True))
        ).distinct()

"""Authorization guards shared by identity services (defence in depth: views check too).

``actor=None`` means a trusted system action (e.g. automatic lockout); user-initiated flows
always pass the acting user.
"""

from __future__ import annotations

from apps.common.exceptions import PermissionDeniedException

from ..models import User
from .permission_service import PermissionService


def authorize(actor: User | None, permission: str) -> None:
    if actor is None:
        return
    if not actor.is_active:
        raise PermissionDeniedException()
    PermissionService.require(actor, permission)


def assert_not_self(actor: User | None, target: User, message: str) -> None:
    if actor is not None and actor.pk == target.pk:
        raise PermissionDeniedException(message)


def assert_can_manage(actor: User | None, target: User) -> None:
    """Only superusers may administer superuser accounts."""
    if actor is not None and target.is_superuser and not actor.is_superuser:
        raise PermissionDeniedException("Only a superuser can manage a superuser account.")

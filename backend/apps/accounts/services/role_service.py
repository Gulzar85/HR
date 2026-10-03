"""Roles, groups and their assignment to users.

Rules enforced here (not in views):
* ``accounts.manage_roles`` to create/edit roles & groups & assign them; ``accounts.manage_permissions``
  to change the permissions they carry.
* No self-service privilege changes; no granting or stripping permissions the actor does not hold
  (privilege-escalation guard); only superusers touch superuser accounts.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError
from django.db.models import Q

from apps.audit.services import record_audit
from apps.common.exceptions import BusinessRuleException, ConflictException, ValidationException
from apps.common.request_context import SYSTEM_CONTEXT, RequestContext
from apps.common.services import transactional

from ..models import AccountEvent, GroupProfile, Role, User, UserRole
from .guards import assert_can_manage, assert_not_self, authorize
from .permission_service import PermissionService, perm_label
from .security_events import record_account_event

MANAGE_ROLES = "accounts.manage_roles"
MANAGE_PERMISSIONS = "accounts.manage_permissions"
MANAGE_USERS = "accounts.manage_users"


def _labels(perms: Iterable[Permission]) -> list[str]:
    return sorted(perm_label(p) for p in perms)


def _role_perms(role: Role) -> list[Permission]:
    return list(role.permissions.select_related("content_type"))


def _group_perms(group: Group) -> list[Permission]:
    return list(group.permissions.select_related("content_type"))


class RoleService:
    # ------------------------------------------------------------------ roles
    @classmethod
    @transactional
    def create_role(
        cls,
        *,
        actor: User,
        name: str,
        code: str,
        description: str = "",
        permissions: Iterable[Permission] = (),
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Role:
        authorize(actor, MANAGE_ROLES)
        perms = list(permissions)
        if perms:
            authorize(actor, MANAGE_PERMISSIONS)
            PermissionService.assert_can_grant(actor, perms)
        if Role.objects.filter(Q(name__iexact=name) | Q(code=code)).exists():
            raise ConflictException("A role with this name or code already exists.")
        try:
            role = Role.objects.create(name=name.strip(), code=code, description=description)
        except IntegrityError as exc:
            raise ConflictException("A role with this name or code already exists.") from exc
        role.permissions.set(perms)
        record_audit(
            action="accounts.role_created",
            actor=actor,
            obj_type="role",
            obj_id=str(role.pk),
            changes={
                "after": {"name": role.name, "code": role.code, "permissions": _labels(perms)}
            },
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return role

    @classmethod
    @transactional
    def update_role(
        cls,
        *,
        actor: User,
        role: Role,
        name: str,
        description: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Role:
        authorize(actor, MANAGE_ROLES)
        if Role.objects.filter(name__iexact=name).exclude(pk=role.pk).exists():
            raise ConflictException("A role with this name already exists.")
        before = {"name": role.name, "description": role.description}
        role.name, role.description = name.strip(), description
        role.save(update_fields=["name", "description", "updated_at"])
        record_audit(
            action="accounts.role_updated",
            actor=actor,
            obj_type="role",
            obj_id=str(role.pk),
            changes={
                "before": before,
                "after": {"name": role.name, "description": role.description},
            },
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return role

    @classmethod
    @transactional
    def set_role_active(
        cls, *, actor: User, role: Role, active: bool, ctx: RequestContext = SYSTEM_CONTEXT
    ) -> Role:
        authorize(actor, MANAGE_ROLES)
        PermissionService.assert_can_grant(actor, _role_perms(role))
        if role.is_active != active:
            role.is_active = active
            role.save(update_fields=["is_active", "updated_at"])
            record_audit(
                action="accounts.role_activated" if active else "accounts.role_deactivated",
                actor=actor,
                obj_type="role",
                obj_id=str(role.pk),
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
            )
        return role

    @classmethod
    @transactional
    def set_role_permissions(
        cls,
        *,
        actor: User,
        role: Role,
        permissions: Iterable[Permission],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> Role:
        authorize(actor, MANAGE_PERMISSIONS)
        new = list(permissions)
        old = _role_perms(role)
        changed = {p.pk for p in new} ^ {p.pk for p in old}
        by_pk = {p.pk: p for p in [*new, *old]}
        PermissionService.assert_can_grant(actor, [by_pk[pk] for pk in changed])
        role.permissions.set(new)
        if changed:
            record_audit(
                action="accounts.role_permissions_changed",
                actor=actor,
                obj_type="role",
                obj_id=str(role.pk),
                changes={"before": _labels(old), "after": _labels(new)},
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
            )
        return role

    # ------------------------------------------------------------ user <-> roles
    @classmethod
    @transactional
    def set_user_roles(
        cls,
        *,
        actor: User,
        user: User,
        roles: Iterable[Role],
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> User:
        authorize(actor, MANAGE_USERS)
        assert_not_self(actor, user, "You cannot change your own roles.")
        assert_can_manage(actor, user)
        new = {r.pk: r for r in roles}
        current = {
            ur.role_id: ur.role for ur in UserRole.objects.filter(user=user).select_related("role")
        }
        added = [new[pk] for pk in new.keys() - current.keys()]
        removed = [current[pk] for pk in current.keys() - new.keys()]
        for role in added:
            if not role.is_active:
                raise BusinessRuleException(
                    f"Role '{role.name}' is inactive and cannot be assigned."
                )
        touched = [p for r in [*added, *removed] for p in _role_perms(r)]
        PermissionService.assert_can_grant(actor, touched)
        for role in removed:
            UserRole.objects.filter(user=user, role=role).delete()
            record_account_event(
                AccountEvent.EventType.ROLE_REMOVED,
                target=user,
                actor=actor,
                before={"role": role.code},
                reason=reason,
                ctx=ctx,
            )
        for role in added:
            UserRole.objects.create(user=user, role=role, assigned_by=actor)
            record_account_event(
                AccountEvent.EventType.ROLE_ASSIGNED,
                target=user,
                actor=actor,
                after={"role": role.code},
                reason=reason,
                ctx=ctx,
            )
        _invalidate_perm_cache(user)
        return user

    # ------------------------------------------------------------------ groups
    @classmethod
    @transactional
    def create_group(
        cls, *, actor: User, name: str, description: str = "", ctx: RequestContext = SYSTEM_CONTEXT
    ) -> GroupProfile:
        authorize(actor, MANAGE_ROLES)
        name = name.strip()
        if not name:
            raise ValidationException("A group name is required.")
        if Group.objects.filter(name__iexact=name).exists():
            raise ConflictException("A group with this name already exists.")
        group = Group.objects.create(name=name)  # signal creates the profile
        profile = group.profile
        profile.description = description
        profile.save(update_fields=["description", "updated_at"])
        record_audit(
            action="accounts.group_created",
            actor=actor,
            obj_type="group",
            obj_id=str(profile.pk),
            changes={"after": {"name": name}},
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return profile

    @classmethod
    @transactional
    def update_group(
        cls,
        *,
        actor: User,
        profile: GroupProfile,
        name: str,
        description: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> GroupProfile:
        authorize(actor, MANAGE_ROLES)
        name = name.strip()
        if Group.objects.filter(name__iexact=name).exclude(pk=profile.group_id).exists():
            raise ConflictException("A group with this name already exists.")
        before = {"name": profile.group.name, "description": profile.description}
        profile.group.name = name
        profile.group.save(update_fields=["name"])
        profile.description = description
        profile.save(update_fields=["description", "updated_at"])
        record_audit(
            action="accounts.group_updated",
            actor=actor,
            obj_type="group",
            obj_id=str(profile.pk),
            changes={"before": before, "after": {"name": name, "description": description}},
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return profile

    @classmethod
    @transactional
    def set_group_active(
        cls,
        *,
        actor: User,
        profile: GroupProfile,
        active: bool,
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> GroupProfile:
        authorize(actor, MANAGE_ROLES)
        PermissionService.assert_can_grant(actor, _group_perms(profile.group))
        if profile.is_active != active:
            profile.is_active = active
            profile.save(update_fields=["is_active", "updated_at"])
            record_audit(
                action="accounts.group_activated" if active else "accounts.group_deactivated",
                actor=actor,
                obj_type="group",
                obj_id=str(profile.pk),
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
            )
        return profile

    @classmethod
    @transactional
    def set_group_permissions(
        cls,
        *,
        actor: User,
        profile: GroupProfile,
        permissions: Iterable[Permission],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> GroupProfile:
        authorize(actor, MANAGE_PERMISSIONS)
        new = list(permissions)
        old = _group_perms(profile.group)
        changed = {p.pk for p in new} ^ {p.pk for p in old}
        by_pk = {p.pk: p for p in [*new, *old]}
        PermissionService.assert_can_grant(actor, [by_pk[pk] for pk in changed])
        profile.group.permissions.set(new)
        if changed:
            record_audit(
                action="accounts.group_permissions_changed",
                actor=actor,
                obj_type="group",
                obj_id=str(profile.pk),
                changes={"before": _labels(old), "after": _labels(new)},
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
            )
        return profile

    @classmethod
    @transactional
    def set_user_groups(
        cls,
        *,
        actor: User,
        user: User,
        groups: Iterable[Group],
        reason: str = "",
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> User:
        authorize(actor, MANAGE_USERS)
        assert_not_self(actor, user, "You cannot change your own groups.")
        assert_can_manage(actor, user)
        new = {g.pk: g for g in groups}
        current = {g.pk: g for g in user.groups.all()}
        added = [new[pk] for pk in new.keys() - current.keys()]
        removed = [current[pk] for pk in current.keys() - new.keys()]
        for group in added:
            if not group.profile.is_active:
                raise BusinessRuleException(f"Group '{group.name}' is inactive.")
        PermissionService.assert_can_grant(
            actor, [p for g in [*added, *removed] for p in _group_perms(g)]
        )
        for group in removed:
            user.groups.remove(group)
            record_account_event(
                AccountEvent.EventType.GROUP_REMOVED,
                target=user,
                actor=actor,
                before={"group": group.name},
                reason=reason,
                ctx=ctx,
            )
        for group in added:
            user.groups.add(group)
            record_account_event(
                AccountEvent.EventType.GROUP_ADDED,
                target=user,
                actor=actor,
                after={"group": group.name},
                reason=reason,
                ctx=ctx,
            )
        _invalidate_perm_cache(user)
        return user

    @classmethod
    def add_group_member(
        cls, *, actor: User, profile: GroupProfile, user: User, ctx: RequestContext = SYSTEM_CONTEXT
    ):
        return cls.set_user_groups(
            actor=actor, user=user, groups=[*user.groups.all(), profile.group], ctx=ctx
        )

    @classmethod
    def remove_group_member(
        cls, *, actor: User, profile: GroupProfile, user: User, ctx: RequestContext = SYSTEM_CONTEXT
    ):
        keep = [g for g in user.groups.all() if g.pk != profile.group_id]
        return cls.set_user_groups(actor=actor, user=user, groups=keep, ctx=ctx)

    @classmethod
    @transactional
    def set_group_members(
        cls,
        *,
        actor: User,
        profile: GroupProfile,
        users: Iterable[User],
        ctx: RequestContext = SYSTEM_CONTEXT,
    ) -> GroupProfile:
        """Membership edited from the group side; delegates per-user so every change is audited."""
        authorize(actor, MANAGE_USERS)
        authorize(actor, MANAGE_ROLES)
        wanted = {u.pk: u for u in users}
        current = {u.pk: u for u in profile.group.user_set.all()}
        for pk in wanted.keys() - current.keys():
            u = wanted[pk]
            cls.set_user_groups(
                actor=actor, user=u, groups=[*u.groups.all(), profile.group], ctx=ctx
            )
        for pk in current.keys() - wanted.keys():
            u = current[pk]
            cls.set_user_groups(
                actor=actor,
                user=u,
                groups=[g for g in u.groups.all() if g.pk != profile.group_id],
                ctx=ctx,
            )
        return profile


def _invalidate_perm_cache(user: User) -> None:
    for attr in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
        if hasattr(user, attr):
            delattr(user, attr)

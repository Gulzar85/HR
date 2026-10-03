from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group, Permission
from django.utils import timezone

from apps.accounts.models import AccountEvent, GroupProfile, Role, UserScope
from apps.accounts.seed import seed_roles
from apps.accounts.services import PermissionService, RoleService, ScopeService, register_scope_type
from apps.accounts.services.scope_service import registered_scope_types, restore_scope_type
from apps.audit.models import AuditLog
from apps.common.exceptions import (
    BusinessRuleException,
    ConflictException,
    NotFoundException,
    PermissionDeniedException,
    ValidationException,
)

pytestmark = pytest.mark.django_db


def perm(label):
    app, codename = label.split(".")
    return Permission.objects.get(content_type__app_label=app, codename=codename)


# ----------------------------------------------------------------------------- roles
def test_role_lifecycle_and_permissions(admin_user, make_user):
    role = RoleService.create_role(
        actor=admin_user,
        name="Auditors Plus",
        code="auditors-plus",
        permissions=[perm("accounts.view_user")],
    )
    member = make_user("m@example.com")
    assert not PermissionService.can(member, "accounts.view_user")

    RoleService.set_user_roles(actor=admin_user, user=member, roles=[role])
    member = type(member).objects.get(pk=member.pk)  # fresh instance: no permission cache
    assert PermissionService.can(member, "accounts.view_user")
    assert AccountEvent.objects.filter(user=member, event_type="role_assigned").exists()

    RoleService.set_role_permissions(actor=admin_user, role=role, permissions=[])
    member = type(member).objects.get(pk=member.pk)
    assert not PermissionService.can(member, "accounts.view_user")

    RoleService.set_role_permissions(
        actor=admin_user, role=role, permissions=[perm("accounts.view_user")]
    )
    RoleService.set_role_active(actor=admin_user, role=role, active=False)
    member = type(member).objects.get(pk=member.pk)
    assert not PermissionService.can(member, "accounts.view_user")  # inactive role grants nothing

    RoleService.set_user_roles(actor=admin_user, user=member, roles=[])
    assert AccountEvent.objects.filter(user=member, event_type="role_removed").exists()
    assert AuditLog.objects.filter(action="accounts.role_permissions_changed").count() == 2


def test_role_names_are_unique_case_insensitively(admin_user):
    RoleService.create_role(actor=admin_user, name="Recruiter X", code="rx")
    with pytest.raises(ConflictException):
        RoleService.create_role(actor=admin_user, name="recruiter x", code="rx2")


def test_cannot_assign_inactive_role(admin_user, make_user):
    role = Role.objects.create(name="Old", code="old", is_active=False)
    with pytest.raises(BusinessRuleException):
        RoleService.set_user_roles(actor=admin_user, user=make_user(), roles=[role])


def test_role_management_requires_permissions(normal_user, make_user):
    with pytest.raises(PermissionDeniedException):
        RoleService.create_role(actor=normal_user, name="Hax", code="hax")
    only_roles = make_user(perms=["accounts.manage_roles"])
    role = RoleService.create_role(actor=only_roles, name="Plain", code="plain")
    with pytest.raises(PermissionDeniedException):  # manage_roles alone cannot set permissions
        RoleService.set_role_permissions(
            actor=only_roles, role=role, permissions=[perm("accounts.view_user")]
        )


def test_privilege_escalation_guard(make_user):
    delegate = make_user(
        perms=["accounts.manage_roles", "accounts.manage_permissions", "accounts.view_user"]
    )
    role = RoleService.create_role(
        actor=delegate, name="Limited", code="limited", permissions=[perm("accounts.view_user")]
    )
    with pytest.raises(PermissionDeniedException):  # does not hold manage_users
        RoleService.set_role_permissions(
            actor=delegate,
            role=role,
            permissions=[perm("accounts.view_user"), perm("accounts.manage_users")],
        )
    with pytest.raises(PermissionDeniedException):
        PermissionService.assert_can_grant(delegate, [perm("accounts.add_user")])


def test_cannot_change_own_roles_or_permissions(admin_user):
    role = Role.objects.create(name="Self", code="self")
    with pytest.raises(PermissionDeniedException):
        RoleService.set_user_roles(actor=admin_user, user=admin_user, roles=[role])
    with pytest.raises(PermissionDeniedException):
        PermissionService.set_user_permissions(actor=admin_user, user=admin_user, permissions=[])


def test_cannot_strip_a_role_you_do_not_outrank(admin_user, make_user):
    low = make_user(perms=["accounts.manage_users"])
    victim = make_user()
    RoleService.set_user_roles(
        actor=admin_user, user=victim, roles=[Role.objects.get(user_roles__user=admin_user)]
    )
    with pytest.raises(PermissionDeniedException):
        RoleService.set_user_roles(actor=low, user=victim, roles=[])


def test_direct_user_permissions_audited(admin_user, make_user):
    target = make_user()
    PermissionService.set_user_permissions(
        actor=admin_user, user=target, permissions=[perm("accounts.view_user")]
    )
    assert AccountEvent.objects.filter(user=target, event_type="permission_changed").exists()
    assert "accounts.view_user" in PermissionService.effective_permissions(
        type(target).objects.get(pk=target.pk)
    )


def test_seed_roles_is_idempotent_and_editable(admin_user):
    first = seed_roles()
    second = seed_roles()
    assert first["created"] >= 13 and second["created"] == 0
    admin_role = Role.objects.get(code="system-administrator")
    assert admin_role.permissions.filter(codename="manage_users").exists()
    assert Role.objects.get(code="auditor").permissions.filter(codename="view_audit_logs").exists()


# ---------------------------------------------------------------------------- groups
def test_group_lifecycle(admin_user, make_user):
    profile = RoleService.create_group(
        actor=admin_user, name="Hiring Panel", description="Interviewers"
    )
    assert isinstance(profile, GroupProfile) and profile.pk.version == 4
    RoleService.set_group_permissions(
        actor=admin_user, profile=profile, permissions=[perm("accounts.view_user")]
    )
    member = make_user()
    RoleService.add_group_member(actor=admin_user, profile=profile, user=member)
    member = type(member).objects.get(pk=member.pk)
    assert PermissionService.can(member, "accounts.view_user")

    RoleService.set_group_active(actor=admin_user, profile=profile, active=False)
    member = type(member).objects.get(pk=member.pk)
    assert not PermissionService.can(member, "accounts.view_user")  # inactive group grants nothing

    RoleService.update_group(actor=admin_user, profile=profile, name="Interview Panel")
    profile.refresh_from_db()
    assert profile.group.name == "Interview Panel"
    RoleService.remove_group_member(actor=admin_user, profile=profile, user=member)
    assert member.groups.count() == 0
    assert (
        AccountEvent.objects.filter(
            user=member, event_type__in=["group_added", "group_removed"]
        ).count()
        == 2
    )


def test_group_names_unique_and_profile_autocreated(admin_user):
    g = Group.objects.create(name="Created Elsewhere")
    assert GroupProfile.objects.filter(group=g).exists()
    with pytest.raises(ConflictException):
        RoleService.create_group(actor=admin_user, name="created elsewhere")


def test_cannot_add_to_inactive_group(admin_user, make_user):
    profile = RoleService.create_group(actor=admin_user, name="Closed")
    RoleService.set_group_active(actor=admin_user, profile=profile, active=False)
    with pytest.raises(BusinessRuleException):
        RoleService.add_group_member(actor=admin_user, profile=profile, user=make_user())


# ----------------------------------------------------------------------------- scopes
# Generic scope mechanics are tested with test-only scope types ("zone" > "sector" > "site") so they
# stay independent of the Organization domain, which registers the real types with validators.


@pytest.fixture(autouse=True)
def _test_scope_types():
    for name in ("zone", "sector", "site"):
        register_scope_type(name, name.title())
    yield
    from apps.accounts.services import scope_service

    for name in ("zone", "sector", "site"):
        scope_service._REGISTRY.pop(name, None)

def test_grant_and_revoke_scope(admin_user, make_user):
    target = make_user()
    scope = ScopeService.grant_scope(
        actor=_super(make_user), user=target, scope_type="zone", scope_ref="REG-001"
    )
    assert ScopeService.has_scope(target, "zone", "REG-001")
    assert not ScopeService.has_scope(target, "zone", "REG-002")
    assert AccountEvent.objects.filter(user=target, event_type="scope_granted").exists()
    ScopeService.revoke_scope(actor=_super(make_user), user=target, scope_id=scope.pk)
    assert not ScopeService.has_scope(target, "zone", "REG-001")
    assert AccountEvent.objects.filter(user=target, event_type="scope_revoked").exists()


def _super(make_user):
    return make_user(f"su{timezone.now().timestamp()}@example.com", superuser=True)


def test_scope_validation(make_user):
    su, target = _super(make_user), make_user()
    with pytest.raises(ValidationException):
        ScopeService.grant_scope(actor=su, user=target, scope_type="galaxy", scope_ref="x")
    with pytest.raises(ValidationException):
        ScopeService.grant_scope(actor=su, user=target, scope_type="zone", scope_ref="")
    with pytest.raises(ValidationException):
        ScopeService.grant_scope(actor=su, user=target, scope_type="zone", scope_ref="*")
    g = ScopeService.grant_scope(actor=su, user=target, scope_type="global", scope_ref="anything")
    assert g.scope_ref == "*"


def test_scope_registry_supports_phase2_validators(make_user):
    su, target = _super(make_user), make_user()
    original = registered_scope_types()["sector"]
    try:
        register_scope_type("sector", "Sector", validator=lambda ref: ref.startswith("AREA-"))
        with pytest.raises(ValidationException):
            ScopeService.grant_scope(actor=su, user=target, scope_type="sector", scope_ref="bogus")
        ScopeService.grant_scope(actor=su, user=target, scope_type="sector", scope_ref="AREA-LHR-001")
    finally:
        restore_scope_type(original)


def test_scope_cannot_be_self_granted_or_exceed_actor(make_user):
    manager = make_user(perms=["accounts.manage_users"])
    other = make_user()
    with pytest.raises(PermissionDeniedException):
        ScopeService.grant_scope(actor=manager, user=manager, scope_type="global", scope_ref="*")
    with pytest.raises(PermissionDeniedException):  # manager holds no scopes at all
        ScopeService.grant_scope(actor=manager, user=other, scope_type="zone", scope_ref="REG-9")
    ScopeService.grant_scope(
        actor=_super(make_user), user=manager, scope_type="zone", scope_ref="REG-9"
    )
    ScopeService.grant_scope(
        actor=manager, user=other, scope_type="zone", scope_ref="REG-9"
    )  # within own
    with pytest.raises(PermissionDeniedException):
        ScopeService.grant_scope(actor=manager, user=other, scope_type="zone", scope_ref="REG-8")


def test_revoke_scope_is_bound_to_user(make_user):
    su, a, b = _super(make_user), make_user(), make_user()
    scope = ScopeService.grant_scope(actor=su, user=a, scope_type="zone", scope_ref="R1")
    with pytest.raises(NotFoundException):  # scope id of A cannot be revoked through B (IDOR)
        ScopeService.revoke_scope(actor=su, user=b, scope_id=scope.pk)
    assert UserScope.objects.filter(pk=scope.pk).exists()


def test_expired_scope_is_ignored(make_user):
    su, target = _super(make_user), make_user()
    ScopeService.grant_scope(
        actor=su,
        user=target,
        scope_type="zone",
        scope_ref="R1",
        expires_at=timezone.now() - timedelta(days=1),
    )
    assert not ScopeService.can_access_scope(target, "zone", "R1")


def test_descendant_resolution_via_registered_expander(make_user):
    su, target = _super(make_user), make_user()
    tree = {
        "REG-1": [("sector", "AREA-1"), ("site", "RST-1")],
        "AREA-1": [("site", "RST-1")],
    }
    original = registered_scope_types()["zone"]
    try:
        register_scope_type("zone", "Zone", descendants=lambda ref: tree.get(ref, []))
        ScopeService.grant_scope(actor=su, user=target, scope_type="zone", scope_ref="REG-1")
        assert ScopeService.can_access_scope(target, "site", "RST-1")
        assert not ScopeService.can_access_scope(target, "site", "RST-2")
        assert ScopeService.accessible_refs(target)["site"] == {"RST-1"}
    finally:
        restore_scope_type(original)


def test_filter_queryset_by_scope_fails_closed(make_user):
    """Uses auth.Group as a stand-in model: its name column plays the scoped reference."""
    su, target, nobody = _super(make_user), make_user(), make_user()
    for n in ("G-A", "G-B", "G-C"):
        Group.objects.create(name=n)
    lookups = {"site": "name"}
    qs = Group.objects.all()
    assert (
        ScopeService.filter_queryset_by_scope(nobody, qs, lookups).count() == 0
    )  # no scope: nothing
    ScopeService.grant_scope(actor=su, user=target, scope_type="site", scope_ref="G-B")
    assert set(
        ScopeService.filter_queryset_by_scope(target, qs, lookups).values_list("name", flat=True)
    ) == {"G-B"}
    ScopeService.grant_scope(actor=su, user=nobody, scope_type="global", scope_ref="*")
    assert ScopeService.filter_queryset_by_scope(nobody, qs, lookups).count() == 3
    assert ScopeService.filter_queryset_by_scope(su, qs, lookups).count() == 3  # superuser
    # a scope type without a lookup for this model grants nothing
    ScopeService.grant_scope(actor=su, user=target, scope_type="sector", scope_ref="G-A")
    assert ScopeService.filter_queryset_by_scope(target, qs, {"sector": "name"}).count() == 1


# ------------------------------------------------------------------ object permissions
def test_object_level_permissions_with_guardian(make_user):
    a, b = make_user(), make_user()
    g1, g2 = Group.objects.create(name="Obj-1"), Group.objects.create(name="Obj-2")
    assert not PermissionService.can_access_object(a, "auth.change_group", g1)
    PermissionService.grant_object_permission(a, "auth.change_group", g1)
    a = type(a).objects.get(pk=a.pk)
    assert PermissionService.can_access_object(a, "auth.change_group", g1)
    assert not PermissionService.can_access_object(a, "auth.change_group", g2)  # other object
    assert not PermissionService.can_access_object(b, "auth.change_group", g1)  # other user
    ids = PermissionService.objects_for_user(a, "auth.change_group", Group.objects.all())
    assert list(ids) == [g1]
    PermissionService.revoke_object_permission(a, "auth.change_group", g1)
    assert not PermissionService.can_access_object(
        type(a).objects.get(pk=a.pk), "auth.change_group", g1
    )


def test_permission_service_denies_anonymous_and_inactive(make_user):
    from django.contrib.auth.models import AnonymousUser

    assert not PermissionService.can(AnonymousUser(), "accounts.view_user")
    assert not PermissionService.can(None, "accounts.view_user")
    inactive = make_user(superuser=True, status="suspended")
    assert not PermissionService.can(
        inactive, "accounts.view_user"
    )  # even superusers when inactive

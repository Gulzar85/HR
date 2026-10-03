"""Role and group administration (CBVs). Raw Django permission screens are never exposed."""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.views.generic import DetailView, ListView

from apps.common.exceptions import NotFoundException

from ...forms import AddMemberForm, GroupForm, PermissionSelectionForm, RoleForm
from ...models import User
from ...permissions import MANAGE_PERMISSIONS, MANAGE_ROLES, VIEW_ROLE
from ...selectors.permission_selectors import grouped_permissions, permissions_from_ids
from ...selectors.role_selectors import GroupSelector, RoleSelector
from ...services import PermissionService, RoleService
from ..base import AdminAccessMixin, PostActionView, ServiceFormView

ROLES_URL = "accounts:role_list"
GROUPS_URL = "accounts:group_list"


# ----------------------------------------------------------------------------- roles
class RoleListView(AdminAccessMixin, ListView):
    permission_required = VIEW_ROLE
    template_name = "accounts/roles/list.html"
    context_object_name = "roles"
    nav_section = "roles"

    def get_queryset(self):
        return RoleSelector.list_roles()

    def get_breadcrumbs(self):
        return [("Administration", None), ("Roles", None)]

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["can_manage"] = PermissionService.can(self.request.user, MANAGE_ROLES)
        return data


class RoleObjectMixin:
    nav_section = "roles"

    def get_role(self):
        if not hasattr(self, "_role"):
            self._role = RoleSelector.get_role(self.kwargs["pk"])  # type: ignore[attr-defined]
        return self._role

    def crumbs(self, last: str):
        r = self.get_role()
        return [
            ("Administration", None),
            ("Roles", reverse(ROLES_URL)),
            (r.name, reverse("accounts:role_detail", args=[r.pk])),
            (last, None),
        ]


class RoleDetailView(RoleObjectMixin, AdminAccessMixin, DetailView):
    permission_required = VIEW_ROLE
    template_name = "accounts/roles/detail.html"
    context_object_name = "role"

    def get_object(self, queryset=None):
        return self.get_role()

    def get_breadcrumbs(self):
        return [
            ("Administration", None),
            ("Roles", reverse(ROLES_URL)),
            (self.get_role().name, None),
        ]

    def get_context_data(self, **kwargs: Any):
        data = super().get_context_data(**kwargs)
        viewer = self.request.user
        role = self.get_role()
        data.update(
            can_manage=PermissionService.can(viewer, MANAGE_ROLES),
            can_permissions=PermissionService.can(viewer, MANAGE_PERMISSIONS),
            permission_groups=grouped_permissions(role.permissions.values_list("pk", flat=True)),
            role_users=RoleSelector.role_users(role)[:50],
            role_user_total=RoleSelector.role_users(role).count(),
        )
        return data


class RoleCreateView(RoleObjectMixin, ServiceFormView):
    permission_required = MANAGE_ROLES
    form_class = RoleForm
    page_title = "Create role"
    submit_label = "Create role"
    success_message = "Role created."
    cancel_url = "/admin/roles/"

    def get_breadcrumbs(self):
        return [("Administration", None), ("Roles", reverse(ROLES_URL)), ("Create", None)]

    def perform(self, form):
        d = form.cleaned_data
        self.created = RoleService.create_role(
            actor=self.request.user,
            name=d["name"],
            code=d["code"],
            description=d["description"],
            ctx=self.ctx,
        )

    def get_success_url(self):
        return reverse("accounts:role_permissions", args=[self.created.pk])


class RoleUpdateView(RoleObjectMixin, ServiceFormView):
    permission_required = MANAGE_ROLES
    form_class = RoleForm
    page_title = "Edit role"
    success_message = "Role updated."

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["instance"] = self.get_role()
        return kw

    def get_initial(self):
        r = self.get_role()
        return {"name": r.name, "code": r.code, "description": r.description}

    def get_breadcrumbs(self):
        return self.crumbs("Edit")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["cancel_url"] = self.get_success_url()
        return data

    def perform(self, form):
        d = form.cleaned_data
        RoleService.update_role(
            actor=self.request.user,
            role=self.get_role(),
            name=d["name"],
            description=d["description"],
            ctx=self.ctx,
        )

    def get_success_url(self):
        return reverse("accounts:role_detail", args=[self.kwargs["pk"]])


class RoleToggleActiveView(RoleObjectMixin, PostActionView):
    permission_required = MANAGE_ROLES
    nav_section = "roles"

    def perform(self, request, *args, **kwargs):
        role = self.get_role()
        RoleService.set_role_active(
            actor=request.user, role=role, active=not role.is_active, ctx=self.ctx
        )
        self.success_message = "Role deactivated." if role.is_active else "Role activated."

    def get_success_url(self, *args, **kwargs):
        return reverse("accounts:role_detail", args=[self.kwargs["pk"]])


class _PermissionMatrixView(ServiceFormView):
    """Checkbox matrix of assignable permissions shared by roles and groups."""

    permission_required = MANAGE_PERMISSIONS
    template_name = "accounts/permission_matrix.html"
    form_class = PermissionSelectionForm
    page_title = "Permissions"
    submit_label = "Save permissions"
    success_message = "Permissions updated."

    def current_ids(self) -> list[int]:  # pragma: no cover - abstract
        raise NotImplementedError

    def subject_label(self) -> str:  # pragma: no cover
        raise NotImplementedError

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["assignable_ids"] = list(
            PermissionService.assignable_permissions().values_list("pk", flat=True)
        )
        return kw

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            selected = {int(i) for i in self.request.POST.getlist("permissions") if i.isdigit()}
        else:
            selected = set(self.current_ids())
        data.update(permission_groups=grouped_permissions(selected), subject=self.subject_label())
        data["cancel_url"] = self.get_success_url()
        return data


class RolePermissionsView(RoleObjectMixin, _PermissionMatrixView):
    def current_ids(self):
        return list(self.get_role().permissions.values_list("pk", flat=True))

    def subject_label(self):
        return f"Role: {self.get_role().name}"

    def get_breadcrumbs(self):
        return self.crumbs("Permissions")

    def perform(self, form):
        RoleService.set_role_permissions(
            actor=self.request.user,
            role=self.get_role(),
            permissions=permissions_from_ids(form.cleaned_data["permissions"]),
            ctx=self.ctx,
        )

    def get_success_url(self):
        return reverse("accounts:role_detail", args=[self.kwargs["pk"]])


# ---------------------------------------------------------------------------- groups
class GroupListView(AdminAccessMixin, ListView):
    permission_required = VIEW_ROLE
    template_name = "accounts/groups/list.html"
    context_object_name = "groups"
    nav_section = "groups"

    def get_queryset(self):
        return GroupSelector.list_groups()

    def get_breadcrumbs(self):
        return [("Administration", None), ("Groups", None)]

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["can_manage"] = PermissionService.can(self.request.user, MANAGE_ROLES)
        return data


class GroupObjectMixin:
    nav_section = "groups"

    def get_profile(self):
        if not hasattr(self, "_profile"):
            self._profile = GroupSelector.get_group(self.kwargs["pk"])  # type: ignore[attr-defined]
        return self._profile

    def crumbs(self, last: str):
        p = self.get_profile()
        return [
            ("Administration", None),
            ("Groups", reverse(GROUPS_URL)),
            (p.group.name, reverse("accounts:group_detail", args=[p.pk])),
            (last, None),
        ]


class GroupDetailView(GroupObjectMixin, AdminAccessMixin, DetailView):
    permission_required = VIEW_ROLE
    template_name = "accounts/groups/detail.html"
    context_object_name = "profile"

    def get_object(self, queryset=None):
        return self.get_profile()

    def get_breadcrumbs(self):
        return [
            ("Administration", None),
            ("Groups", reverse(GROUPS_URL)),
            (self.get_profile().group.name, None),
        ]

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        viewer = self.request.user
        profile = self.get_profile()
        members = GroupSelector.members(profile)
        data.update(
            can_manage=PermissionService.can(viewer, MANAGE_ROLES),
            can_permissions=PermissionService.can(viewer, MANAGE_PERMISSIONS),
            members=members[:100],
            member_total=members.count(),
            permission_groups=grouped_permissions(
                profile.group.permissions.values_list("pk", flat=True)
            ),
            add_form=AddMemberForm(),
        )
        return data


class GroupCreateView(GroupObjectMixin, ServiceFormView):
    permission_required = MANAGE_ROLES
    form_class = GroupForm
    page_title = "Create group"
    submit_label = "Create group"
    success_message = "Group created."
    cancel_url = "/admin/groups/"

    def get_breadcrumbs(self):
        return [("Administration", None), ("Groups", reverse(GROUPS_URL)), ("Create", None)]

    def perform(self, form):
        d = form.cleaned_data
        self.created = RoleService.create_group(
            actor=self.request.user, name=d["name"], description=d["description"], ctx=self.ctx
        )

    def get_success_url(self):
        return reverse("accounts:group_detail", args=[self.created.pk])


class GroupUpdateView(GroupObjectMixin, ServiceFormView):
    permission_required = MANAGE_ROLES
    form_class = GroupForm
    page_title = "Edit group"
    success_message = "Group updated."

    def get_initial(self):
        p = self.get_profile()
        return {"name": p.group.name, "description": p.description}

    def get_breadcrumbs(self):
        return self.crumbs("Edit")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["cancel_url"] = self.get_success_url()
        return data

    def perform(self, form):
        d = form.cleaned_data
        RoleService.update_group(
            actor=self.request.user,
            profile=self.get_profile(),
            name=d["name"],
            description=d["description"],
            ctx=self.ctx,
        )

    def get_success_url(self):
        return reverse("accounts:group_detail", args=[self.kwargs["pk"]])


class GroupToggleActiveView(GroupObjectMixin, PostActionView):
    permission_required = MANAGE_ROLES

    def perform(self, request, *args, **kwargs):
        p = self.get_profile()
        RoleService.set_group_active(
            actor=request.user, profile=p, active=not p.is_active, ctx=self.ctx
        )
        self.success_message = "Group deactivated." if p.is_active else "Group activated."

    def get_success_url(self, *args, **kwargs):
        return reverse("accounts:group_detail", args=[self.kwargs["pk"]])


class GroupPermissionsView(GroupObjectMixin, _PermissionMatrixView):
    def current_ids(self):
        return list(self.get_profile().group.permissions.values_list("pk", flat=True))

    def subject_label(self):
        return f"Group: {self.get_profile().group.name}"

    def get_breadcrumbs(self):
        return self.crumbs("Permissions")

    def perform(self, form):
        RoleService.set_group_permissions(
            actor=self.request.user,
            profile=self.get_profile(),
            permissions=permissions_from_ids(form.cleaned_data["permissions"]),
            ctx=self.ctx,
        )

    def get_success_url(self):
        return reverse("accounts:group_detail", args=[self.kwargs["pk"]])


class GroupAddMemberView(GroupObjectMixin, PostActionView):
    permission_required = MANAGE_ROLES
    success_message = "Member added."

    def perform(self, request, *args, **kwargs):
        form = AddMemberForm(request.POST)
        if not form.is_valid():
            raise NotFoundException("Enter a valid email address.")
        user = User.objects.filter(email=form.cleaned_data["email"].lower()).first()
        if user is None:
            raise NotFoundException("No user with that email.")
        RoleService.add_group_member(
            actor=request.user, profile=self.get_profile(), user=user, ctx=self.ctx
        )

    def get_success_url(self, *args, **kwargs):
        return reverse("accounts:group_detail", args=[self.kwargs["pk"]])


class GroupRemoveMemberView(GroupObjectMixin, PostActionView):
    permission_required = MANAGE_ROLES
    success_message = "Member removed."

    def perform(self, request, *args, **kwargs):
        user = User.objects.filter(pk=kwargs["user_id"], groups=self.get_profile().group).first()
        if user is None:
            raise NotFoundException("That user is not a member of this group.")
        RoleService.remove_group_member(
            actor=request.user, profile=self.get_profile(), user=user, ctx=self.ctx
        )

    def get_success_url(self, *args, **kwargs):
        return reverse("accounts:group_detail", args=[self.kwargs["pk"]])

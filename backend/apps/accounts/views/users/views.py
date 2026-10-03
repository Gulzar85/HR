from __future__ import annotations

from typing import Any

from django.conf import settings
from django.urls import reverse
from django.views.generic import DetailView, TemplateView
from django_filters.views import FilterView

from apps.audit.models import AuditLog  # noqa: F401  (history shown via selector)
from apps.common.exceptions import NotFoundException
from apps.common.views.mixins import HtmxTemplateMixin

from ...filters import UserFilter
from ...forms import (
    AdminSetPasswordForm,
    ScopeGrantForm,
    StatusActionForm,
    UserCreateForm,
    UserEditForm,
    UserGroupsForm,
    UserRolesForm,
)
from ...models import User
from ...permissions import (
    ADD_USER,
    CHANGE_USER,
    MANAGE_USERS,
    VIEW_SECURITY_HISTORY,
    VIEW_USER,
)
from ...selectors.user_selectors import UserSelector
from ...services import PermissionService, RoleService, ScopeService, SessionService, UserService
from ..base import AdminAccessMixin, PostActionView, ServiceFormView


class UserListView(AdminAccessMixin, HtmxTemplateMixin, FilterView):
    permission_required = VIEW_USER
    filterset_class = UserFilter
    template_name = "accounts/users/list.html"
    htmx_template_name = "accounts/users/_table.html"
    context_object_name = "users"
    strict = False

    def get_paginate_by(self, queryset) -> int:
        return settings.EMS_ADMIN_PAGE_SIZE

    def get_queryset(self):
        return UserSelector.list_users()

    def get_breadcrumbs(self):
        return [("Administration", None), ("Users", None)]

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        data["querystring"] = params.urlencode()
        return data


class UserObjectMixin:
    """Resolve the target user from the URL (UUID); authorization is checked by the mixin/service."""

    def get_target(self) -> User:
        if not hasattr(self, "_target"):
            self._target = UserSelector.get_user(self.kwargs["pk"])  # type: ignore[attr-defined]
        return self._target

    def user_breadcrumbs(self, last: str) -> list[tuple[str, str | None]]:
        t = self.get_target()
        return [
            ("Administration", None),
            ("Users", reverse("accounts:user_list")),
            (t.display_name, reverse("accounts:user_detail", args=[t.pk])),
            (last, None),
        ]


class UserDetailView(UserObjectMixin, AdminAccessMixin, DetailView):
    permission_required = VIEW_USER
    template_name = "accounts/users/detail.html"
    context_object_name = "target"

    def get_object(self, queryset=None):
        return self.get_target()

    def get_breadcrumbs(self):
        return [
            ("Administration", None),
            ("Users", reverse("accounts:user_list")),
            (self.get_target().display_name, None),
        ]

    def get_context_data(self, **kwargs: Any):
        data = super().get_context_data(**kwargs)
        target = self.get_target()
        viewer = self.request.user
        can_history = PermissionService.can(viewer, VIEW_SECURITY_HISTORY)
        can_manage = PermissionService.can(viewer, MANAGE_USERS)
        data.update(
            scopes=UserSelector.scopes_for(target),
            can_manage=can_manage,
            can_edit=PermissionService.can(viewer, CHANGE_USER),
            can_history=can_history,
            is_self=viewer.pk == target.pk,
            effective_permissions=PermissionService.effective_permissions(target)
            if can_manage
            else [],
            status_form=StatusActionForm(),
            direct_permission_count=target.user_permissions.count(),
        )
        if can_history:
            data["recent_logins"] = UserSelector.recent_logins(target)
            data["recent_audit"] = UserSelector.recent_audit(target)
        return data


class UserCreateView(ServiceFormView):
    permission_required = ADD_USER
    form_class = UserCreateForm
    page_title = "Create user"
    submit_label = "Create user"
    success_message = "User created."
    cancel_url = "/admin/users/"

    def get_breadcrumbs(self):
        return [
            ("Administration", None),
            ("Users", reverse("accounts:user_list")),
            ("Create", None),
        ]

    def perform(self, form):
        d = form.cleaned_data
        self.created = UserService.create_user(
            actor=self.request.user,
            email=d["email"],
            first_name=d["first_name"],
            last_name=d["last_name"],
            username=d["username"] or None,
            password=d["initial_password"] or None,
            roles=d["roles"],
            groups=d["groups"],
            ctx=self.ctx,
        )

    def get_success_url(self):
        return reverse("accounts:user_detail", args=[self.created.pk])


class UserUpdateView(UserObjectMixin, ServiceFormView):
    permission_required = CHANGE_USER
    form_class = UserEditForm
    page_title = "Edit user"
    success_message = "User updated."

    def get_initial(self):
        t = self.get_target()
        return {
            "email": t.email,
            "first_name": t.first_name,
            "last_name": t.last_name,
            "username": t.username,
        }

    def get_breadcrumbs(self):
        return self.user_breadcrumbs("Edit")

    def cancel(self):
        return reverse("accounts:user_detail", args=[self.kwargs["pk"]])

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["cancel_url"] = self.cancel()
        return data

    def perform(self, form):
        UserService.update_user(
            actor=self.request.user, user=self.get_target(), ctx=self.ctx, **form.cleaned_data
        )

    def get_success_url(self):
        return self.cancel()


class UserStatusView(UserObjectMixin, PostActionView):
    permission_required = MANAGE_USERS

    def perform(self, request, *args, **kwargs):
        form = StatusActionForm(request.POST)
        if not form.is_valid():
            raise NotFoundException("Invalid status action.")
        user = UserService.apply_action(
            self.get_target(),
            form.cleaned_data["action"],
            actor=request.user,
            reason=form.cleaned_data["reason"],
            ctx=self.ctx,
        )
        self.success_message = f"Account is now {user.get_status_display().lower()}."

    def get_success_url(self, *args, **kwargs):
        return reverse("accounts:user_detail", args=[self.kwargs["pk"]])


class UserRolesView(UserObjectMixin, ServiceFormView):
    permission_required = MANAGE_USERS
    form_class = UserRolesForm
    page_title = "Assign roles"
    success_message = "Roles updated."
    template_name = "accounts/users/assign.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.get_target()
        return kw

    def get_initial(self):
        return {"roles": list(self.get_target().roles.values_list("pk", flat=True))}

    def get_breadcrumbs(self):
        return self.user_breadcrumbs("Roles")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["cancel_url"] = reverse("accounts:user_detail", args=[self.kwargs["pk"]])
        data["target"] = self.get_target()
        return data

    def perform(self, form):
        RoleService.set_user_roles(
            actor=self.request.user,
            user=self.get_target(),
            roles=form.cleaned_data["roles"],
            ctx=self.ctx,
        )

    def get_success_url(self):
        return reverse("accounts:user_detail", args=[self.kwargs["pk"]])


class UserGroupsView(UserRolesView):
    form_class = UserGroupsForm
    page_title = "Assign groups"
    success_message = "Groups updated."

    def get_initial(self):
        return {"groups": list(self.get_target().groups.values_list("pk", flat=True))}

    def get_breadcrumbs(self):
        return self.user_breadcrumbs("Groups")

    def perform(self, form):
        RoleService.set_user_groups(
            actor=self.request.user,
            user=self.get_target(),
            groups=form.cleaned_data["groups"],
            ctx=self.ctx,
        )


class UserScopesView(UserObjectMixin, ServiceFormView):
    permission_required = MANAGE_USERS
    form_class = ScopeGrantForm
    page_title = "Access scopes"
    submit_label = "Grant scope"
    success_message = "Scope granted."
    template_name = "accounts/users/scopes.html"

    def get_breadcrumbs(self):
        return self.user_breadcrumbs("Scopes")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(target=self.get_target(), scopes=UserSelector.scopes_for(self.get_target()))
        return data

    def perform(self, form):
        d = form.cleaned_data
        ScopeService.grant_scope(
            actor=self.request.user,
            user=self.get_target(),
            scope_type=d["scope_type"],
            scope_ref=d["scope_ref"],
            include_descendants=d["include_descendants"],
            expires_at=d["expires_at"],
            ctx=self.ctx,
        )

    def get_success_url(self):
        return reverse("accounts:user_scopes", args=[self.kwargs["pk"]])


class UserScopeRevokeView(UserObjectMixin, PostActionView):
    permission_required = MANAGE_USERS
    success_message = "Scope revoked."

    def perform(self, request, *args, **kwargs):
        ScopeService.revoke_scope(
            actor=request.user, user=self.get_target(), scope_id=kwargs["scope_id"], ctx=self.ctx
        )

    def get_success_url(self, *args, **kwargs):
        return reverse("accounts:user_scopes", args=[self.kwargs["pk"]])


class UserSetPasswordView(UserObjectMixin, ServiceFormView):
    permission_required = MANAGE_USERS
    form_class = AdminSetPasswordForm
    page_title = "Set password"
    success_message = "Password set. The user's sessions were ended."

    def get_breadcrumbs(self):
        return self.user_breadcrumbs("Set password")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["cancel_url"] = reverse("accounts:user_detail", args=[self.kwargs["pk"]])
        return data

    def perform(self, form):
        UserService.set_password_by_admin(
            actor=self.request.user,
            user=self.get_target(),
            password=form.cleaned_data["password"],
            ctx=self.ctx,
        )

    def get_success_url(self):
        return reverse("accounts:user_detail", args=[self.kwargs["pk"]])


class UserSendResetView(UserObjectMixin, PostActionView):
    permission_required = MANAGE_USERS
    success_message = "A password link was sent to the user."

    def perform(self, request, *args, **kwargs):
        UserService.send_password_reset(actor=request.user, user=self.get_target(), ctx=self.ctx)

    def get_success_url(self, *args, **kwargs):
        return reverse("accounts:user_detail", args=[self.kwargs["pk"]])


class UserRevokeSessionsView(UserObjectMixin, PostActionView):
    permission_required = MANAGE_USERS
    success_message = "All sessions were revoked."

    def perform(self, request, *args, **kwargs):
        from ...services.guards import assert_can_manage

        target = self.get_target()
        assert_can_manage(request.user, target)
        SessionService.revoke_all(target, reason="revoked_by_admin")
        from ...models import AccountEvent
        from ...services.security_events import record_account_event

        record_account_event(
            AccountEvent.EventType.SESSION_REVOKED,
            target=target,
            actor=request.user,
            after={"scope": "all_sessions"},
            ctx=self.ctx,
        )

    def get_success_url(self, *args, **kwargs):
        return reverse("accounts:user_detail", args=[self.kwargs["pk"]])


class UserSecurityHistoryView(UserObjectMixin, AdminAccessMixin, TemplateView):
    permission_required = VIEW_SECURITY_HISTORY
    template_name = "accounts/users/security_history.html"

    def get_breadcrumbs(self):
        return self.user_breadcrumbs("Security history")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(
            target=self.get_target(), history=UserSelector.security_history(self.get_target())
        )
        return data

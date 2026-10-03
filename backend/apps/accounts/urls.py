"""All accounts web URLs, mounted at the site root with explicit paths (see docs)."""

from django.urls import path

from .views.auth import views as auth
from .views.profile import views as profile
from .views.roles import views as roles
from .views.users import views as users

app_name = "accounts"

urlpatterns = [
    # authentication
    path("accounts/login/", auth.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth.LogoutView.as_view(), name="logout"),
    path("accounts/password/change/", auth.PasswordChangeView.as_view(), name="password_change"),
    path(
        "accounts/password/change/done/",
        auth.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path("accounts/password/reset/", auth.PasswordResetView.as_view(), name="password_reset"),
    path(
        "accounts/password/reset/done/",
        auth.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "accounts/password/reset/<uidb64>/<token>/",
        auth.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "accounts/password/reset/complete/",
        auth.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    # self-service
    path("profile/", profile.ProfileView.as_view(), name="profile"),
    path("profile/sessions/", profile.SessionListView.as_view(), name="sessions"),
    path(
        "profile/sessions/<uuid:pk>/revoke/",
        profile.SessionRevokeView.as_view(),
        name="session_revoke",
    ),
    # user administration
    path("admin/users/", users.UserListView.as_view(), name="user_list"),
    path("admin/users/create/", users.UserCreateView.as_view(), name="user_create"),
    path("admin/users/<uuid:pk>/", users.UserDetailView.as_view(), name="user_detail"),
    path("admin/users/<uuid:pk>/edit/", users.UserUpdateView.as_view(), name="user_edit"),
    path("admin/users/<uuid:pk>/status/", users.UserStatusView.as_view(), name="user_status"),
    path("admin/users/<uuid:pk>/roles/", users.UserRolesView.as_view(), name="user_roles"),
    path("admin/users/<uuid:pk>/groups/", users.UserGroupsView.as_view(), name="user_groups"),
    path("admin/users/<uuid:pk>/scopes/", users.UserScopesView.as_view(), name="user_scopes"),
    path(
        "admin/users/<uuid:pk>/scopes/<uuid:scope_id>/revoke/",
        users.UserScopeRevokeView.as_view(),
        name="user_scope_revoke",
    ),
    path(
        "admin/users/<uuid:pk>/password/",
        users.UserSetPasswordView.as_view(),
        name="user_set_password",
    ),
    path(
        "admin/users/<uuid:pk>/password/send-link/",
        users.UserSendResetView.as_view(),
        name="user_send_reset",
    ),
    path(
        "admin/users/<uuid:pk>/sessions/revoke/",
        users.UserRevokeSessionsView.as_view(),
        name="user_revoke_sessions",
    ),
    path(
        "admin/users/<uuid:pk>/security/",
        users.UserSecurityHistoryView.as_view(),
        name="user_security",
    ),
    # roles
    path("admin/roles/", roles.RoleListView.as_view(), name="role_list"),
    path("admin/roles/create/", roles.RoleCreateView.as_view(), name="role_create"),
    path("admin/roles/<uuid:pk>/", roles.RoleDetailView.as_view(), name="role_detail"),
    path("admin/roles/<uuid:pk>/edit/", roles.RoleUpdateView.as_view(), name="role_edit"),
    path("admin/roles/<uuid:pk>/toggle/", roles.RoleToggleActiveView.as_view(), name="role_toggle"),
    path(
        "admin/roles/<uuid:pk>/permissions/",
        roles.RolePermissionsView.as_view(),
        name="role_permissions",
    ),
    # groups
    path("admin/groups/", roles.GroupListView.as_view(), name="group_list"),
    path("admin/groups/create/", roles.GroupCreateView.as_view(), name="group_create"),
    path("admin/groups/<uuid:pk>/", roles.GroupDetailView.as_view(), name="group_detail"),
    path("admin/groups/<uuid:pk>/edit/", roles.GroupUpdateView.as_view(), name="group_edit"),
    path(
        "admin/groups/<uuid:pk>/toggle/", roles.GroupToggleActiveView.as_view(), name="group_toggle"
    ),
    path(
        "admin/groups/<uuid:pk>/permissions/",
        roles.GroupPermissionsView.as_view(),
        name="group_permissions",
    ),
    path(
        "admin/groups/<uuid:pk>/members/add/",
        roles.GroupAddMemberView.as_view(),
        name="group_member_add",
    ),
    path(
        "admin/groups/<uuid:pk>/members/<uuid:user_id>/remove/",
        roles.GroupRemoveMemberView.as_view(),
        name="group_member_remove",
    ),
]

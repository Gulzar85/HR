"""Mounted by apps/api/v1/urls.py: /api/v1/{auth,users,roles,permissions,sessions}/."""

from django.urls import path

from . import views as v

auth_urlpatterns = [
    path("token/", v.TokenObtainView.as_view(), name="token"),
    path("token/refresh/", v.TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", v.LogoutView.as_view(), name="logout"),
    path("me/", v.MeView.as_view(), name="me"),
    path("password/change/", v.PasswordChangeAPIView.as_view(), name="password-change"),
]
user_urlpatterns = [
    path("", v.UserListCreateView.as_view(), name="user-list"),
    path("<uuid:pk>/", v.UserDetailView.as_view(), name="user-detail"),
    path("<uuid:pk>/status/", v.UserStatusView.as_view(), name="user-status"),
]
role_urlpatterns = [
    path("", v.RoleListCreateView.as_view(), name="role-list"),
    path("<uuid:pk>/", v.RoleDetailView.as_view(), name="role-detail"),
]
permission_urlpatterns = [path("", v.PermissionListView.as_view(), name="permission-list")]
session_urlpatterns = [
    path("", v.SessionListView.as_view(), name="session-list"),
    path("<uuid:pk>/", v.SessionRevokeView.as_view(), name="session-revoke"),
]

"""REST endpoints for identity: /api/v1/auth|users|roles|permissions|sessions.

Thin adapters over the services; permissions come from ``HasPerm`` + service-level checks.
"""

from __future__ import annotations

from django.utils.text import slugify
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.api.permissions import HasPerm
from apps.api.responses import success
from apps.common.request_context import RequestContext

from ..filters import UserFilter
from ..models import LoginEvent, Role, User
from ..selectors.role_selectors import RoleSelector
from ..selectors.user_selectors import UserSelector
from ..services import (
    AuthenticationService,
    PermissionService,
    RoleService,
    ScopeService,
    SessionService,
    UserService,
)
from ..services.security_events import record_login_event
from . import serializers as s


class BearerChallengeMixin:
    """Views without authentication classes still answer auth failures with 401 + challenge."""

    def get_authenticate_header(self, request) -> str:
        return 'Bearer realm="api"'


_ctx = RequestContext.from_request  # request -> RequestContext (IP, user agent, base URL)


# ------------------------------------------------------------------------------ auth
class TokenObtainView(BearerChallengeMixin, APIView):
    """POST email+password -> short-lived access token + rotating refresh token."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = s.LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = AuthenticationService.api_login(
            request=request,
            email=ser.validated_data["email"],
            password=ser.validated_data["password"],
            ctx=_ctx(request),
        )
        refresh = RefreshToken.for_user(user)
        return success(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "token_type": "Bearer",
                "expires_in": int(jwt_settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
            }
        )


class TokenRefreshView(BearerChallengeMixin, APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = s.RefreshSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            old = RefreshToken(
                ser.validated_data["refresh"]
            )  # verifies signature, expiry, blacklist
            user = User.objects.get(pk=old[jwt_settings.USER_ID_CLAIM])
            if not user.is_active:  # suspended/inactive/locked accounts cannot refresh
                raise InvalidToken("Account is not active.")
            old.blacklist()  # rotation: each refresh token is single-use
            new = RefreshToken.for_user(user)
        except (TokenError, User.DoesNotExist) as exc:
            raise InvalidToken(str(exc)) from exc
        return success(
            {
                "access": str(new.access_token),
                "refresh": str(new),
                "token_type": "Bearer",
                "expires_in": int(jwt_settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
            }
        )


class LogoutView(BearerChallengeMixin, APIView):
    """Revoke a refresh token (server-side blacklist)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        ser = s.RefreshSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            token = RefreshToken(ser.validated_data["refresh"])
            user = User.objects.filter(pk=token[jwt_settings.USER_ID_CLAIM]).first()
            token.blacklist()
        except TokenError as exc:
            raise InvalidToken(str(exc)) from exc
        if user:
            record_login_event(
                LoginEvent.EventType.LOGOUT, user=user, channel="api", ctx=_ctx(request)
            )
        return success({"detail": "Signed out."}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return success(
            {
                **s.UserSerializer(user).data,
                "permissions": PermissionService.effective_permissions(user),
                "scopes": [
                    {
                        "type": sc.scope_type,
                        "ref": sc.scope_ref,
                        "include_descendants": sc.include_descendants,
                    }
                    for sc in ScopeService.get_user_scopes(user)
                ],
                "is_superuser": user.is_superuser,
            }
        )


class PasswordChangeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = s.PasswordChangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        AuthenticationService.change_password(
            user=request.user,
            old_password=ser.validated_data["old_password"],
            new_password=ser.validated_data["new_password"],
            ctx=_ctx(request),
        )  # all refresh tokens are blacklisted: sign in again
        return success({"detail": "Password changed. Please sign in again."})


# ------------------------------------------------------------------------------ users
class UserListCreateView(generics.ListCreateAPIView):
    permission_classes = [HasPerm]
    permission_map = {"GET": "accounts.view_user", "POST": "accounts.add_user"}
    filterset_class = UserFilter
    serializer_class = s.UserSerializer

    def get_queryset(self):
        return UserSelector.list_users()

    def create(self, request, *args, **kwargs):
        ser = s.UserCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        user = UserService.create_user(
            actor=request.user,
            email=d["email"],
            first_name=d["first_name"],
            last_name=d["last_name"],
            username=d.get("username") or None,
            password=d.get("password") or None,
            roles=d["role_ids"],
            groups=d["group_ids"],
            ctx=_ctx(request),
        )
        return success(s.UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [HasPerm]
    permission_map = {
        "GET": "accounts.view_user",
        "PATCH": "accounts.change_user",
        "PUT": "accounts.change_user",
    }
    serializer_class = s.UserSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return UserSelector.get_user(self.kwargs["pk"])

    def patch(self, request, *args, **kwargs):
        ser = s.UserUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        user = UserService.update_user(
            actor=request.user, user=self.get_object(), ctx=_ctx(request), **ser.validated_data
        )
        return success(s.UserSerializer(user).data)


class UserStatusView(APIView):
    permission_classes = [HasPerm]
    permission_map = {"POST": "accounts.manage_users"}

    def post(self, request, pk):
        ser = s.StatusActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = UserService.apply_action(
            UserSelector.get_user(pk),
            ser.validated_data["action"],
            actor=request.user,
            reason=ser.validated_data["reason"],
            ctx=_ctx(request),
        )
        return success(s.UserSerializer(user).data)


# ------------------------------------------------------------------------------ roles
class RoleListCreateView(generics.ListCreateAPIView):
    permission_classes = [HasPerm]
    permission_map = {"GET": "accounts.view_role", "POST": "accounts.manage_roles"}
    serializer_class = s.RoleSerializer

    def get_queryset(self):
        return RoleSelector.list_roles().prefetch_related("permissions__content_type")

    def create(self, request, *args, **kwargs):
        ser = s.RoleWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        role = RoleService.create_role(
            actor=request.user,
            name=d["name"],
            code=d.get("code") or slugify(d["name"]),
            description=d["description"],
            permissions=d.get("permissions", []),
            ctx=_ctx(request),
        )
        return success(s.RoleSerializer(role).data, status=status.HTTP_201_CREATED)


class RoleDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [HasPerm]
    permission_map = {"GET": "accounts.view_role", "PATCH": "accounts.manage_roles"}
    serializer_class = s.RoleSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return RoleSelector.get_role(self.kwargs["pk"])

    def patch(self, request, *args, **kwargs):
        role: Role = self.get_object()
        ser = s.RoleWriteSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if "name" in d or "description" in d:
            RoleService.update_role(
                actor=request.user,
                role=role,
                name=d.get("name", role.name),
                description=d.get("description", role.description),
                ctx=_ctx(request),
            )
        if "permissions" in d:  # requires accounts.manage_permissions (checked in the service)
            RoleService.set_role_permissions(
                actor=request.user, role=role, permissions=d["permissions"], ctx=_ctx(request)
            )
        return success(s.RoleSerializer(RoleSelector.get_role(role.pk)).data)


class PermissionListView(generics.ListAPIView):
    permission_classes = [HasPerm]
    permission_map = {"GET": "accounts.view_role"}
    serializer_class = s.PermissionSerializer

    def get_queryset(self):
        return PermissionService.assignable_permissions()


# --------------------------------------------------------------------------- sessions
class SessionListView(generics.ListAPIView):
    """The caller's own active web sessions."""

    permission_classes = [IsAuthenticated]
    serializer_class = s.SessionSerializer

    def get_queryset(self):
        return SessionService.active_sessions(self.request.user)


class SessionRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        SessionService.revoke_session(pk, actor=request.user, owner=request.user, ctx=_ctx(request))
        return success({"detail": "Session revoked."})

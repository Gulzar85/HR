from __future__ import annotations

from rest_framework import serializers

from ..models import Role, User, UserSession
from ..selectors.role_selectors import GroupSelector
from ..services.permission_service import PermissionService, perm_label


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SlugRelatedField(many=True, read_only=True, slug_field="code")
    groups = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")

    class Meta:
        model = User
        fields = [
            "id", "email", "username", "first_name", "last_name", "status",
            "is_active", "last_login", "date_joined", "roles", "groups",
        ]  # fmt: skip
        read_only_fields = fields


class UserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, allow_blank=True, default="")
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, trim_whitespace=False
    )
    role_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    group_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)

    def validate_role_ids(self, ids):
        roles = list(Role.objects.filter(pk__in=ids))
        if len(roles) != len(set(ids)):
            raise serializers.ValidationError("Unknown role id.")
        return roles

    def validate_group_ids(self, ids):
        groups = list(GroupSelector.active_groups().filter(profile__pk__in=ids))
        if len(groups) != len(set(ids)):
            raise serializers.ValidationError("Unknown or inactive group id.")
        return groups


class UserUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    username = serializers.CharField(max_length=150, required=False)


class StatusActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["activate", "deactivate", "suspend", "unlock"])
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "name", "code", "description", "is_active", "is_system", "permissions"]
        read_only_fields = ["id", "is_system", "permissions"]

    def get_permissions(self, role) -> list[str]:
        return sorted(perm_label(p) for p in role.permissions.all())


class RoleWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    code = serializers.SlugField(max_length=60, required=False)
    description = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    permissions = serializers.ListField(child=serializers.CharField(), required=False)

    def validate_permissions(self, labels):
        return PermissionService.resolve_permissions(labels)


class PermissionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.SerializerMethodField()
    name = serializers.CharField()

    def get_label(self, p) -> str:
        return perm_label(p)


class SessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = ["id", "created_at", "ip_address", "user_agent"]  # never the session key
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

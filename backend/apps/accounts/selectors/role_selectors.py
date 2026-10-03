from __future__ import annotations

from typing import Any

from django.contrib.auth.models import Group
from django.db.models import Count, QuerySet
from django.shortcuts import get_object_or_404

from ..models import GroupProfile, Role, User


class RoleSelector:
    @staticmethod
    def list_roles() -> QuerySet[Role]:
        return Role.objects.annotate(
            user_count=Count("user_roles", distinct=True),
            permission_count=Count("permissions", distinct=True),
        ).order_by("name")

    @staticmethod
    def active_roles() -> QuerySet[Role]:
        return Role.objects.filter(is_active=True).order_by("name")

    @staticmethod
    def get_role(pk: Any) -> Role:
        return get_object_or_404(Role.objects.prefetch_related("permissions__content_type"), pk=pk)

    @staticmethod
    def role_users(role: Role) -> QuerySet[User]:
        return User.objects.filter(user_roles__role=role).defer("password").order_by("email")


class GroupSelector:
    @staticmethod
    def list_groups() -> QuerySet[GroupProfile]:
        return (
            GroupProfile.objects.select_related("group")
            .annotate(
                member_count=Count("group__user", distinct=True),
                permission_count=Count("group__permissions", distinct=True),
            )
            .order_by("group__name")
        )

    @staticmethod
    def active_groups() -> QuerySet[Group]:
        return Group.objects.filter(profile__is_active=True).order_by("name")

    @staticmethod
    def get_group(pk: Any) -> GroupProfile:
        return get_object_or_404(
            GroupProfile.objects.select_related("group").prefetch_related(
                "group__permissions__content_type"
            ),
            pk=pk,
        )

    @staticmethod
    def members(profile: GroupProfile) -> QuerySet[User]:
        return profile.group.user_set.defer("password").order_by("email")

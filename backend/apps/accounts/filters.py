"""django-filter FilterSets for the admin lists and API (filtering stays out of templates)."""

from __future__ import annotations

import django_filters as df
from django.contrib.auth.models import Group
from django.db.models import Q

from .models import Role, User, UserStatus


class UserFilter(df.FilterSet):
    q = df.CharFilter(method="search", label="Search")
    status = df.ChoiceFilter(choices=UserStatus.choices, label="Status")
    role = df.ModelChoiceFilter(
        queryset=Role.objects.filter(is_active=True), method="filter_role", label="Role"
    )
    group = df.ModelChoiceFilter(
        queryset=Group.objects.filter(profile__is_active=True), method="filter_group", label="Group"
    )
    is_active = df.BooleanFilter(label="Can sign in")
    joined = df.DateFromToRangeFilter(field_name="date_joined", label="Date joined")
    last_login = df.DateFromToRangeFilter(field_name="last_login", label="Last login")
    ordering = df.OrderingFilter(
        fields=(
            ("first_name", "name"),
            ("email", "email"),
            ("status", "status"),
            ("last_login", "last_login"),
            ("date_joined", "created"),
        )
    )

    class Meta:
        model = User
        fields: list[str] = []

    @staticmethod
    def search(queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(email__icontains=value)
            | Q(username__icontains=value)
            | Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
        )

    @staticmethod
    def filter_role(queryset, name, value):
        return queryset.filter(user_roles__role=value).distinct()

    @staticmethod
    def filter_group(queryset, name, value):
        return queryset.filter(groups=value).distinct()

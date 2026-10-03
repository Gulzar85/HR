"""Employee list filters (web + API). The base queryset is already scope-filtered; filters can only
narrow it. Filters over sensitive data are *removed* for users who may not see that data, so they
cannot be used as an oracle (e.g. "filter by gender" without view_sensitive_identity)."""

from __future__ import annotations

import django_filters as df
from django.db.models import Exists, OuterRef

from . import permissions
from .models import Employee, EmployeeIdentifier, EmployeeStatus, Gender, VerificationStatus
from .selectors import search_employees


class EmployeeFilter(df.FilterSet):
    q = df.CharFilter(method="search", label="Search")
    employee_status = df.ChoiceFilter(choices=EmployeeStatus.choices, label="Status")
    gender = df.ChoiceFilter(field_name="person__gender", choices=Gender.choices, label="Gender")
    has_user = df.BooleanFilter(method="filter_has_user", label="Has user account")
    created = df.DateFromToRangeFilter(field_name="created_at", label="Created")
    verification_status = df.ChoiceFilter(
        choices=VerificationStatus.choices,
        method="filter_verification",
        label="Identifier verification",
    )
    ordering = df.OrderingFilter(
        fields=(
            ("code", "code"),
            ("person__last_name", "name"),
            ("employee_status", "status"),
            ("created_at", "created"),
        )
    )

    class Meta:
        model = Employee
        fields: list[str] = []

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, request=request, **kwargs)
        user = getattr(request, "user", None)
        if not permissions.can_view_sensitive_identity(user):
            self.filters.pop("gender", None)
        if not permissions.can_view_identifiers(user):
            self.filters.pop("verification_status", None)

    def search(self, queryset, name, value):
        return search_employees(getattr(self.request, "user", None), queryset, value)

    @staticmethod
    def filter_has_user(queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(user__isnull=not value)

    @staticmethod
    def filter_verification(queryset, name, value):
        return queryset.filter(
            Exists(
                EmployeeIdentifier.objects.filter(
                    employee=OuterRef("pk"), verification_status=value
                )
            )
        )

"""Reusable DRF permission classes. Backend authorization is authoritative (ADR-012).

Declare per-method permissions on the view and fail closed when a method is not mapped:

    class EmployeeListView(ListAPIView):
        permission_classes = [HasPerm]
        permission_map = {"GET": "employees.view_employee"}
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.accounts.services import PermissionService


class HasPerm(BasePermission):
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view) -> bool:
        required = getattr(view, "permission_map", {}).get(request.method)
        if required is None:
            return False  # fail closed
        return PermissionService.can(request.user, required)

    def has_object_permission(self, request, view, obj) -> bool:
        required = getattr(view, "permission_map", {}).get(request.method)
        return required is not None and PermissionService.can_access_object(
            request.user, required, obj
        )

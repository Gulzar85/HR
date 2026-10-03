"""Reusable CBV mixins. Views handle HTTP only; business logic lives in services/selectors."""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import QuerySet
from django.utils.cache import patch_vary_headers

from apps.common.permissions import apply_scope


class EMSPermissionMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Login + Django permission check; authenticated users lacking permission get 403."""

    raise_exception = False

    def handle_no_permission(self):
        if self.request.user.is_authenticated:  # type: ignore[attr-defined]
            self.raise_exception = True
        return super().handle_no_permission()


class ScopedQuerysetMixin:
    """Restrict a view's queryset to the requesting user's organization scope."""

    def get_queryset(self) -> QuerySet:
        return apply_scope(self.request.user, super().get_queryset())  # type: ignore[attr-defined,misc]


class HtmxTemplateMixin:
    """Render ``htmx_template_name`` (a partial) for HTMX requests, else the full template."""

    htmx_template_name: str | None = None

    def get_template_names(self) -> list[str]:
        htmx = getattr(self.request, "htmx", None)  # type: ignore[attr-defined]
        if htmx and not htmx.history_restore_request and self.htmx_template_name:
            return [self.htmx_template_name]
        return super().get_template_names()  # type: ignore[misc]

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)  # type: ignore[misc]
        patch_vary_headers(
            response, ["HX-Request"]
        )  # full page vs partial must not share a cache entry
        return response

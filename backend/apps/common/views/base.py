"""Shared admin CBV building blocks (moved from accounts in Phase 2 so every domain can reuse them).

Views handle HTTP only; services decide. Domain errors become form errors or flash messages.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import FormView

from apps.common.exceptions import (
    BusinessRuleException,
    ConflictException,
    DomainException,
    NotFoundException,
    ValidationException,
)
from apps.common.request_context import RequestContext
from apps.common.views.mixins import EMSPermissionMixin

FORM_ERRORS = (ValidationException, ConflictException, BusinessRuleException)


class AdminAccessMixin(EMSPermissionMixin):
    """Login + required permission (backend-enforced; hiding buttons is never relied upon)."""

    nav_section = "users"
    breadcrumbs: list[tuple[str, str | None]] = []

    @property
    def ctx(self) -> RequestContext:
        return RequestContext.from_request(self.request)

    def get_breadcrumbs(self) -> list[tuple[str, str | None]]:
        return self.breadcrumbs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        data = super().get_context_data(**kwargs)  # type: ignore[misc]
        data["breadcrumbs"] = self.get_breadcrumbs()
        data["nav_section"] = self.nav_section
        return data


class ServiceFormView(AdminAccessMixin, FormView):
    """FormView whose submit calls a service; domain errors become form errors."""

    template_name = "accounts/generic_form.html"
    page_title = ""
    submit_label = "Save"
    cancel_url: str | None = None
    success_message = "Saved."

    def perform(self, form) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    def get_success_url(self) -> str:
        raise NotImplementedError

    def form_valid(self, form) -> HttpResponse:
        try:
            self.perform(form)
        except FORM_ERRORS as exc:
            self.add_domain_error(form, exc)
            return self.form_invalid(form)
        if self.success_message:
            messages.success(self.request, self.success_message)
        return redirect(self.get_success_url())

    @staticmethod
    def add_domain_error(form, exc: DomainException) -> None:
        placed = False
        for field, msgs in (exc.details or {}).items():
            if field in form.fields and isinstance(msgs, list):
                for m in msgs:
                    form.add_error(field, m)
                placed = True
        if not placed:
            form.add_error(None, exc.message)
        elif exc.details:
            return

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        data = super().get_context_data(**kwargs)
        data.update(
            page_title=self.page_title,
            submit_label=self.submit_label,
            cancel_url=self.cancel_url,
        )
        return data


class PostActionView(AdminAccessMixin, View):
    """POST-only action (CSRF-protected). GET is rejected; success redirects with a message."""

    http_method_names = ["post"]
    success_message = "Done."

    def perform(self, request, *args, **kwargs) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    def get_success_url(self, *args, **kwargs) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        try:
            self.perform(request, *args, **kwargs)
        except (*FORM_ERRORS, NotFoundException) as exc:
            messages.error(request, exc.message)
        else:
            if self.success_message:
                messages.success(request, self.success_message)
        return redirect(self.get_success_url(*args, **kwargs))

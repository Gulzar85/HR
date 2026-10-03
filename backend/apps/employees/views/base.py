"""Shared building blocks for the employee screens.

* :func:`capabilities` - the one place the UI asks "may this user see/do X?" (always mirrored by a
  server-side check in the service or view; hiding is never the control).
* :func:`section_context` - data for each detail-page section, gated by those capabilities, so the
  full page and every HTMX partial render identical, equally-protected content.
* :class:`EmployeeObjectMixin` - resolves the employee *through the user's scope* (404 otherwise).
* :class:`SectionActionView` - CSRF-protected inline add/change/remove that returns the refreshed
  section for HTMX or redirects for plain form posts.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.accounts.services import PermissionService
from apps.audit.models import AuditLog
from apps.common.exceptions import (
    BusinessRuleException,
    ConflictException,
    DomainException,
    NotFoundException,
    ValidationException,
)
from apps.common.views.base import AdminAccessMixin

from .. import permissions as P
from ..models import NoteVisibility
from ..selectors import (
    get_employee,
    get_employee_addresses,
    get_employee_contacts,
    get_employee_emergency_contacts,
    get_employee_identifiers,
    get_employee_timeline,
)

FORM_ERRORS = (ValidationException, ConflictException, BusinessRuleException)


def capabilities(user: Any) -> dict[str, bool]:
    can = lambda perm: PermissionService.can(user, perm)  # noqa: E731
    sensitive = can(P.VIEW_SENSITIVE_IDENTITY)
    return {
        "change": can(P.CHANGE),
        "change_person": can(P.CHANGE_PERSON),
        "archive": can(P.ARCHIVE),
        "link_user": can(P.LINK_USER),
        "export": can(P.EXPORT),
        "view_sensitive": sensitive,
        "view_identifiers": can(P.VIEW_IDENTIFIERS),
        "reveal_identifiers": sensitive and can(P.VIEW_IDENTIFIERS),
        "view_addresses": can(P.VIEW_SENSITIVE_CONTACTS),
        "view_emergency": can(P.VIEW_EMERGENCY_CONTACTS),
        "view_timeline": can(P.VIEW_TIMELINE),
        "view_audit": can("audit.view_audit_logs"),
        "manage_contacts": can(P.MANAGE_CONTACTS),
        "manage_addresses": can(P.MANAGE_ADDRESSES),
        "manage_emergency": can(P.MANAGE_EMERGENCY_CONTACTS),
        "manage_identifiers": can(P.MANAGE_IDENTIFIERS),
        "manage_notes": can(P.MANAGE_NOTES),
    }


SECTIONS = (
    "identity",
    "contacts",
    "addresses",
    "emergency",
    "identifiers",
    "notes",
    "timeline",
    "account",
)


def section_context(http_request: Any, employee: Any, section: str, **extra: Any) -> dict[str, Any]:
    user = http_request.user
    caps = capabilities(user)
    ctx: dict[str, Any] = {"employee": employee, "person": employee.person, "caps": caps, **extra}
    if section == "identity":
        from ..models import country_label

        ctx["nationality_label"] = country_label(employee.person.nationality)
    elif section == "contacts":
        ctx["contacts"] = list(get_employee_contacts(employee))
    elif section == "addresses" and caps["view_addresses"]:
        ctx["addresses"] = list(get_employee_addresses(employee))
    elif section == "emergency" and caps["view_emergency"]:
        ctx["emergency_contacts"] = list(get_employee_emergency_contacts(employee))
    elif section == "identifiers" and caps["view_identifiers"]:
        ctx["identifiers"] = list(get_employee_identifiers(employee))
    elif section == "notes":
        notes = employee.notes.select_related("created_by").all()
        if not caps["view_sensitive"]:
            notes = notes.exclude(visibility=NoteVisibility.RESTRICTED)
        ctx["notes"] = list(notes)
    elif section == "timeline" and caps["view_timeline"]:
        ctx["timeline"] = get_employee_timeline(user, employee, limit=50)
    elif section == "audit" and caps["view_audit"]:
        ctx["audit"] = list(
            AuditLog.objects.filter(
                object_type="employee", object_id=str(employee.pk)
            ).select_related("actor")[:20]
        )
    return ctx


def detail_context(http_request: Any, employee: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for section in (*SECTIONS, "audit"):
        data.update(section_context(http_request, employee, section))
    return data


class EmployeeObjectMixin:
    """``self.employee`` is always fetched through the user's scope (IDOR protection)."""

    @property
    def employee(self):
        if not hasattr(self, "_employee"):
            self._employee = get_employee(self.request.user, self.kwargs["pk"])  # type: ignore[attr-defined]
        return self._employee

    def employee_crumbs(self, last: str | None = None) -> list[tuple[str, str | None]]:
        emp = self.employee
        crumbs = [
            ("People", None),
            ("Employees", reverse("employees:list")),
            (emp.code, reverse("employees:detail", args=[emp.pk])),
        ]
        return [*crumbs, (last, None)] if last else crumbs


class SectionActionView(EmployeeObjectMixin, AdminAccessMixin, View):
    """Inline section action. Subclasses set ``section``, ``permission_required`` and either a
    ``form_class`` (GET renders the inline form, POST validates then calls :meth:`perform`) or
    ``http_method_names = ["post"]`` with no form (simple action buttons)."""

    section: ClassVar[str]
    form_class: ClassVar[type | None] = None
    success_message: ClassVar[str] = "Saved."
    title: ClassVar[str] = ""

    def get_form_kwargs(self) -> dict[str, Any]:
        return {}

    def perform(self, form: Any) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def form_url(self) -> str:
        return self.request.path

    def render_form(self, form: Any, status: int = 200) -> HttpResponse:
        response = render(
            self.request,
            "employees/sections/_inline_form.html",
            {
                "form": form,
                "employee": self.employee,
                "section": self.section,
                "action_url": self.form_url(),
                "title": self.title,
            },
            status=status,
        )
        if self.request.method == "POST" and getattr(self.request, "htmx", False):
            # Validation errors: replace only the inline form, not the whole section.
            response["HX-Retarget"] = f"#sec-{self.section}-form"
            response["HX-Reswap"] = "innerHTML"
        return response

    def render_section(self) -> HttpResponse:
        employee = get_employee(self.request.user, self.employee.pk)  # fresh, still scoped
        ctx = section_context(self.request, employee, self.section, flash=self.success_message)
        return render(self.request, f"employees/sections/_{self.section}.html", ctx)

    def done(self) -> HttpResponse:
        if getattr(self.request, "htmx", False):
            return self.render_section()
        messages.success(self.request, self.success_message)
        return redirect(
            reverse("employees:detail", args=[self.employee.pk]) + f"#sec-{self.section}"
        )

    def get(self, request, *args, **kwargs):
        if self.form_class is None:
            return HttpResponse(status=405)
        _ = self.employee  # scope check before rendering anything
        return self.render_form(self.form_class(**self.get_form_kwargs()))

    def post(self, request, *args, **kwargs):
        _ = self.employee
        form = None
        if self.form_class is not None:
            form = self.form_class(request.POST, request.FILES, **self.get_form_kwargs())
            if not form.is_valid():
                return self.render_form(form)  # htmx only swaps 2xx responses
        try:
            self.perform(form)
        except FORM_ERRORS as exc:
            if form is None:
                messages.error(request, exc.message)
                return self.done()
            _apply_errors(form, exc)
            return self.render_form(form)  # htmx only swaps 2xx responses
        except NotFoundException:
            raise
        return self.done()


def _apply_errors(form: Any, exc: DomainException) -> None:
    placed = False
    for field, msgs in (exc.details or {}).items():
        if field in form.fields:
            for m in msgs if isinstance(msgs, list) else [msgs]:
                form.add_error(field, m)
            placed = True
    if not placed:
        form.add_error(None, exc.message)


apply_errors = _apply_errors

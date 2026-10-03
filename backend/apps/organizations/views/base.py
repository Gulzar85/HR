"""Generic organization CBVs, parametrised by organization type.

Per-type modules (``views/restaurants/`` etc.) subclass these with their columns, filters and forms.
Every object lookup goes through the user's organization scope (out-of-scope = 404), every write
goes through ``OrganizationService`` (permission + scope + hierarchy rules).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from django.conf import settings
from django.urls import reverse
from django.utils.html import format_html
from django.views.generic import DetailView
from django_filters.views import FilterView

from apps.accounts.services import PermissionService
from apps.common.views.base import AdminAccessMixin, ServiceFormView
from apps.common.views.mixins import HtmxTemplateMixin

from ..filters import FILTERS
from ..forms import FORMS, MoveForm, StatusChangeForm
from ..hierarchy import ORG_TYPES, OrgType, ancestors_of, get_parent, org_type_of
from ..selectors import (
    children_of,
    get_unit_for_user,
    history_for,
    relationships_for,
    visible_units,
)
from ..services import OrganizationService


@dataclass(frozen=True)
class Column:
    label: str
    kind: str = "text"  # unit | parent | status | text | date
    attr: str = ""
    hide_sm: bool = False


def unit_url(obj: Any) -> str:
    return reverse(f"organizations:{org_type_of(obj).key}_detail", args=[obj.pk])


def _resolve(obj: Any, attr: str) -> Any:
    for part in attr.split("."):
        obj = getattr(obj, part, None) if obj is not None else None
        if callable(obj) and not hasattr(obj, "_meta"):
            obj = obj()  # e.g. get_status_display
    return obj


class OrgTypeMixin:
    type_key: ClassVar[str]
    columns: ClassVar[list[Column]] = []
    detail_fields: ClassVar[list[tuple[str, str]]] = []  # noqa: RUF012
    action: ClassVar[str] = "view"

    @property
    def org_type(self) -> OrgType:
        return ORG_TYPES[self.type_key]

    def get_permission_required(self):
        return (self.org_type.perm(self.action),)

    def get_unit(self):
        if not hasattr(self, "_unit"):
            self._unit = get_unit_for_user(self.request.user, self.type_key, self.kwargs["pk"])  # type: ignore[attr-defined]
        return self._unit

    def base_crumbs(self) -> list[tuple[str, str | None]]:
        return [
            ("Organization", reverse("organizations:dashboard")),
            (self.org_type.plural, reverse(f"organizations:{self.type_key}_list")),
        ]

    def unit_crumbs(self, last: str | None = None) -> list[tuple[str, str | None]]:
        unit = self.get_unit()
        crumbs = [*self.base_crumbs(), (unit.code, unit_url(unit))]
        return [*crumbs, (last, None)] if last else crumbs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        data = super().get_context_data(**kwargs)  # type: ignore[misc]
        data["org_type"] = self.org_type
        data["nav_section"] = self.type_key
        return data


# -------------------------------------------------------------------------------- list
class OrgListView(OrgTypeMixin, AdminAccessMixin, HtmxTemplateMixin, FilterView):
    template_name = "organizations/unit_list.html"
    htmx_template_name = "organizations/_unit_table.html"
    context_object_name = "units"
    strict = False

    def get_filterset_class(self):
        return FILTERS[self.type_key]

    def get_paginate_by(self, queryset) -> int:
        return settings.EMS_ADMIN_PAGE_SIZE

    def get_queryset(self):
        return visible_units(self.request.user, self.type_key)

    def get_breadcrumbs(self):
        return [("Organization", reverse("organizations:dashboard")), (self.org_type.plural, None)]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        data = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        data["querystring"] = params.urlencode()
        data["columns"] = self.columns
        data["rows"] = [self._row(obj) for obj in data["units"]]
        data["can_add"] = PermissionService.can(self.request.user, self.org_type.perm("add"))
        return data

    def _row(self, obj: Any) -> dict[str, Any]:
        cells = []
        for col in self.columns:
            value = _resolve(obj, col.attr) if col.attr else obj
            if col.kind == "unit":
                html = format_html(
                    '<a class="cell-title" href="{}">{}</a><span class="cell-sub">{}</span>',
                    unit_url(obj),
                    obj.name,
                    obj.code,
                )
            elif col.kind == "parent":
                html = (
                    format_html(
                        '<a href="{}">{}</a><span class="cell-sub">{}</span>',
                        unit_url(value),
                        value.name,
                        value.code,
                    )
                    if value
                    else "—"
                )
            else:
                html = value if value not in (None, "") else "—"
            cells.append({"kind": col.kind, "value": html, "hide_sm": col.hide_sm, "obj": obj})
        return {"obj": obj, "url": unit_url(obj), "cells": cells}


# ------------------------------------------------------------------------------ detail
class OrgDetailView(OrgTypeMixin, AdminAccessMixin, DetailView):
    template_name = "organizations/unit_detail.html"
    context_object_name = "unit"

    def get_object(self, queryset=None):
        return self.get_unit()

    def get_breadcrumbs(self):
        unit = self.get_unit()
        return [*self.base_crumbs(), (unit.code, None)]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        data = super().get_context_data(**kwargs)
        user, unit, t = self.request.user, self.get_unit(), self.org_type
        service = OrganizationService.for_type(t.key)
        can_status = PermissionService.can(user, "organizations.change_organization_status")
        children = []
        for child_type, qs in children_of(user, unit):
            children.append(
                {
                    "type": child_type,
                    "units": list(qs[:50]),
                    "total": qs.count(),
                    "list_url": (
                        reverse(f"organizations:{child_type.key}_list") + f"?{t.key}={unit.pk}"
                        if t.key in FILTERS[child_type.key].base_filters
                        else None
                    ),
                    "create_url": reverse(f"organizations:{child_type.key}_create")
                    + f"?{child_type.parent_key}={unit.pk}",
                    "can_add": PermissionService.can(user, child_type.perm("add")),
                }
            )
        data.update(
            fields=[(label, _resolve(unit, attr)) for label, attr in self.detail_fields],
            parent=get_parent(unit),
            ancestors=list(reversed(ancestors_of(unit))),
            children=children,
            can_edit=PermissionService.can(user, t.perm("change")),
            can_move=t.parent_key is not None
            and PermissionService.can(user, "organizations.move_organization"),
            status_actions=[
                (a, a.replace("_", " ").capitalize()) for a in service.allowed_actions(unit)
            ]
            if can_status
            else [],
            can_history=PermissionService.can(user, "organizations.view_organization_history"),
        )
        if data["can_history"]:
            data["history"] = history_for(unit)
            data["relationships"] = relationships_for(unit)
        return data


# ------------------------------------------------------------------------------ writes
class OrgCreateView(OrgTypeMixin, ServiceFormView):
    action = "add"
    template_name = "organizations/unit_form.html"

    @property
    def page_title(self) -> str:  # type: ignore[override]
        return f"New {self.org_type.label.lower()}"

    def get_form_class(self):
        return FORMS[self.type_key][0]

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw

    def get_initial(self):
        initial = super().get_initial()
        for key in ORG_TYPES:
            if key in self.request.GET:
                initial[key] = self.request.GET[key]
        return initial

    def get_breadcrumbs(self):
        return [*self.base_crumbs(), ("New", None)]

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["cancel_url"] = reverse(f"organizations:{self.type_key}_list")
        data["submit_label"] = f"Create {self.org_type.label.lower()}"
        return data

    def perform(self, form):
        self.created = OrganizationService.create(
            self.type_key,
            actor=self.request.user,
            data=form.service_data(),
            parent=form.parent(),
            status=form.cleaned_data.get("status") or None,
            ctx=self.ctx,
        )
        self.success_message = f"{self.created.code} created."

    def get_success_url(self):
        return unit_url(self.created)


class OrgUpdateView(OrgTypeMixin, ServiceFormView):
    action = "change"
    template_name = "organizations/unit_form.html"
    success_message = "Changes saved."

    @property
    def page_title(self) -> str:  # type: ignore[override]
        return f"Edit {self.get_unit().code}"

    def get_form_class(self):
        return FORMS[self.type_key][1]

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw.update(user=self.request.user, instance=self.get_unit())
        return kw

    def get_breadcrumbs(self):
        return self.unit_crumbs("Edit")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["cancel_url"] = unit_url(self.get_unit())
        data["unit"] = self.get_unit()
        return data

    def perform(self, form):
        OrganizationService.update(
            self.get_unit(), actor=self.request.user, data=form.service_data(), ctx=self.ctx
        )

    def get_success_url(self):
        return unit_url(self.get_unit())


class OrgStatusView(OrgTypeMixin, ServiceFormView):
    template_name = "organizations/unit_form.html"
    form_class = StatusChangeForm

    def get_permission_required(self):
        return ("organizations.change_organization_status",)

    @property
    def page_title(self) -> str:  # type: ignore[override]
        return f"Change status of {self.get_unit().code}"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["actions"] = OrganizationService.for_type(self.type_key).allowed_actions(self.get_unit())
        return kw

    def get_initial(self):
        return {"action": self.request.GET.get("action")}

    def get_breadcrumbs(self):
        return self.unit_crumbs("Status")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(
            cancel_url=unit_url(self.get_unit()), submit_label="Apply", unit=self.get_unit()
        )
        return data

    def perform(self, form):
        d = form.cleaned_data
        unit = OrganizationService.change_status(
            self.get_unit(),
            d["action"],
            actor=self.request.user,
            reason=d["reason"],
            effective_date=d["effective_date"],
            ctx=self.ctx,
        )
        self.success_message = f"{unit.code} is now {unit.get_status_display().lower()}."

    def get_success_url(self):
        return unit_url(self.get_unit())


class OrgMoveView(OrgTypeMixin, ServiceFormView):
    template_name = "organizations/unit_form.html"
    form_class = MoveForm

    def get_permission_required(self):
        return ("organizations.move_organization",)

    @property
    def page_title(self) -> str:  # type: ignore[override]
        return f"Move {self.get_unit().code}"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw.update(key=self.type_key, obj=self.get_unit(), user=self.request.user)
        return kw

    def get_breadcrumbs(self):
        return self.unit_crumbs("Move")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(
            cancel_url=unit_url(self.get_unit()),
            submit_label="Move",
            unit=self.get_unit(),
            current_parent=get_parent(self.get_unit()),
        )
        return data

    def perform(self, form):
        d = form.cleaned_data
        unit = OrganizationService.move(
            self.get_unit(),
            d[form.parent_key],
            actor=self.request.user,
            reason=d["reason"],
            effective_date=d["effective_date"],
            ctx=self.ctx,
        )
        self.success_message = f"{unit.code} moved to {d[form.parent_key].code}."

    def get_success_url(self):
        return unit_url(self.get_unit())

"""Organization dashboard, dynamic tree and the HTMX cascading-options endpoint."""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.urls import reverse
from django.views.generic import TemplateView

from apps.accounts.services import PermissionService
from apps.common.views.base import AdminAccessMixin

from ...hierarchy import ORG_TYPES, TYPE_ORDER, ancestor_paths
from ...selectors import counts_for, get_organization_tree, visible_units

STRUCTURE_PERM = "organizations.view_organization_structure"


class OrganizationDashboardView(AdminAccessMixin, TemplateView):
    permission_required = STRUCTURE_PERM
    template_name = "organizations/dashboard.html"
    nav_section = "org_dashboard"

    def get_breadcrumbs(self):
        return [("Organization", None)]

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        counts = counts_for(self.request.user)
        user = self.request.user
        data["cards"] = [
            {
                "label": ORG_TYPES[k].plural,
                "icon": ORG_TYPES[k].icon,
                "value": counts[k],
                "url": reverse(f"organizations:{k}_list"),
                "visible": PermissionService.can(user, ORG_TYPES[k].perm("view")),
            }
            for k in TYPE_ORDER
        ]
        data["restaurant_status"] = counts["restaurants_by_status"]
        data["restaurants_active"] = counts["restaurants_active"]
        data["restaurants_inactive"] = counts["restaurants_inactive"]
        return data


class OrganizationTreeView(AdminAccessMixin, TemplateView):
    permission_required = STRUCTURE_PERM
    template_name = "organizations/tree.html"
    nav_section = "org_tree"

    def get_breadcrumbs(self):
        return [("Organization", reverse("organizations:dashboard")), ("Structure tree", None)]

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        include_inactive = self.request.GET.get("inactive") == "1"
        data["tree"] = get_organization_tree(self.request.user, include_inactive=include_inactive)
        data["include_inactive"] = include_inactive
        return data


class OrganizationOptionsView(LoginRequiredMixin, TemplateView):
    """``GET /organizations/options/<child_type>/?<parent_type>=<uuid>`` -> ``<option>`` list.

    Used by cascading selects. Returns only units visible to the user (scope-filtered) and only for
    users who can view that type; the server re-validates every submitted choice anyway.
    """

    template_name = "organizations/_options.html"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        key = self.kwargs["type_key"]
        t = ORG_TYPES.get(key)
        if t is None or not PermissionService.can(self.request.user, t.perm("view")):
            raise Http404
        qs = visible_units(self.request.user, key).filter(
            status__in=["planned", "active", "temporarily_closed"]
        )
        for parent_key, path in ancestor_paths(key).items():
            value = self.request.GET.get(parent_key)
            if value:
                try:
                    qs = qs.filter(**{f"{path}_id": value})
                except Exception as exc:  # malformed id
                    raise Http404 from exc
        data["options"] = qs[:500]
        data["blank_label"] = self.request.GET.get("blank", "---------")
        return data

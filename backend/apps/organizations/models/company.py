from __future__ import annotations

from django.db import models

from .base import OrganizationUnit, OrgStatus, status_check


class Company(OrganizationUnit):
    """Root organizational entity. Multi-company capable data model (not SaaS multi-tenancy)."""

    ORG_TYPE = "company"

    legal_name = models.CharField(max_length=200, blank=True)
    registration_number = models.CharField(max_length=60, blank=True)
    tax_number = models.CharField("tax number (NTN)", max_length=60, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    # Branding is owned by apps.theme. This is only a *reference* to the theme to apply (Phase 6
    # ThemeAssignment will resolve it); no colours or logos are stored here.
    theme_key = models.SlugField(max_length=60, blank=True)

    class Meta(OrganizationUnit.Meta):
        verbose_name_plural = "companies"
        constraints = [
            *OrganizationUnit.Meta.constraints,
            status_check("company", OrgStatus),
        ]
        permissions = [
            (
                "change_organization_status",
                "Can activate, deactivate, close or archive organization units",
            ),
            ("move_organization", "Can move organization units to a different parent"),
            ("view_organization_history", "Can view organization history"),
            ("view_organization_structure", "Can view the organization overview and tree"),
        ]

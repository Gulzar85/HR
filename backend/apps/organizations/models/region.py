from __future__ import annotations

from django.db import models
from django.db.models.functions import Lower

from .base import OrganizationUnit, OrgStatus, status_check
from .division import Division


class Region(OrganizationUnit):
    """An operations region under an OPERATIONS division."""

    ORG_TYPE = "region"

    division = models.ForeignKey(Division, on_delete=models.PROTECT, related_name="regions")

    class Meta(OrganizationUnit.Meta):
        constraints = [
            *OrganizationUnit.Meta.constraints,
            status_check("region", OrgStatus),
            models.UniqueConstraint("division", Lower("name"), name="org_region_division_name"),
        ]

from __future__ import annotations

from django.db import models
from django.db.models.functions import Lower

from .base import OrganizationUnit, OrgStatus, status_check
from .region import Region


class Area(OrganizationUnit):
    ORG_TYPE = "area"

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="areas")

    class Meta(OrganizationUnit.Meta):
        constraints = [
            *OrganizationUnit.Meta.constraints,
            status_check("area", OrgStatus),
            models.UniqueConstraint("region", Lower("name"), name="org_area_region_name"),
        ]

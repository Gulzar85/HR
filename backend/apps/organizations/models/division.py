from __future__ import annotations

from django.db import models
from django.db.models.functions import Lower

from .base import OrganizationUnit, OrgStatus, status_check
from .company import Company


class StructureType(models.TextChoices):
    """The *structural role* of a division in the locked hierarchy.

    Division names ("Corporate", "Operations") are configurable data; the structure type decides
    which children are valid: CORPORATE -> corporate locations -> departments,
    OPERATIONS -> regions -> areas -> restaurants.
    """

    CORPORATE = "corporate", "Corporate (locations & departments)"
    OPERATIONS = "operations", "Operations (regions, areas & restaurants)"


class Division(OrganizationUnit):
    ORG_TYPE = "division"

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="divisions")
    structure_type = models.CharField(max_length=20, choices=StructureType.choices)

    class Meta(OrganizationUnit.Meta):
        constraints = [
            *OrganizationUnit.Meta.constraints,
            status_check("division", OrgStatus),
            models.UniqueConstraint(fields=["company", "code"], name="org_division_company_code"),
            models.UniqueConstraint("company", Lower("name"), name="org_division_company_name"),
            models.CheckConstraint(
                condition=models.Q(structure_type__in=[c.value for c in StructureType]),
                name="org_division_structure_valid",
            ),
        ]

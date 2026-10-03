from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

from .base import OrganizationUnit, OrgStatus, status_check
from .corporate_location import CorporateLocation

SHORT_CODE_VALIDATOR = RegexValidator(r"^[A-Z0-9]{2,8}$", "2-8 upper-case letters/digits, e.g. HR.")


class Department(OrganizationUnit):
    """A department *instance* at one corporate location: Lahore HR and Karachi HR are different
    units (DEPT-LHR-HR, DEPT-KHI-HR)."""

    ORG_TYPE = "department"

    location = models.ForeignKey(
        CorporateLocation, on_delete=models.PROTECT, related_name="departments"
    )
    short_code = models.CharField(max_length=8, validators=[SHORT_CODE_VALIDATOR])

    class Meta(OrganizationUnit.Meta):
        constraints = [
            *OrganizationUnit.Meta.constraints,
            status_check("department", OrgStatus),
            models.UniqueConstraint(
                fields=["location", "short_code"], name="org_department_location_short"
            ),
            models.UniqueConstraint("location", Lower("name"), name="org_department_location_name"),
        ]

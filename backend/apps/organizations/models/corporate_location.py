from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

from .base import OrganizationUnit, OrgStatus, status_check
from .division import Division

CITY_CODE_VALIDATOR = RegexValidator(
    r"^[A-Z]{3}$", "Use a 3-letter upper-case city code, e.g. LHR."
)


class CorporateLocation(OrganizationUnit):
    """A corporate office (e.g. Lahore, Karachi) under a CORPORATE division."""

    ORG_TYPE = "corporate_location"

    division = models.ForeignKey(
        Division, on_delete=models.PROTECT, related_name="corporate_locations"
    )
    city = models.CharField(max_length=80, blank=True)
    city_code = models.CharField(max_length=3, validators=[CITY_CODE_VALIDATOR])
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)

    class Meta(OrganizationUnit.Meta):
        constraints = [
            *OrganizationUnit.Meta.constraints,
            status_check("corporatelocation", OrgStatus),
            models.UniqueConstraint("division", Lower("name"), name="org_location_division_name"),
        ]

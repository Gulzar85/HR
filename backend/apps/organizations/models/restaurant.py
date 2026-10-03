from __future__ import annotations

from decimal import Decimal

from django.db import models

from .area import Area
from .base import OrganizationUnit, RestaurantStatus, status_check
from .corporate_location import CITY_CODE_VALIDATOR


class Restaurant(OrganizationUnit):
    """Lowest unit of the operations hierarchy. Only organizational master data: no sales,
    inventory, staffing, payroll or attendance (those belong to other domains)."""

    ORG_TYPE = "restaurant"

    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="restaurants")
    status = models.CharField(
        max_length=20,
        choices=RestaurantStatus.choices,
        default=RestaurantStatus.PLANNED,
        db_index=True,
    )
    short_name = models.CharField(max_length=60, blank=True)
    city = models.CharField(max_length=80, blank=True)
    city_code = models.CharField(max_length=3, validators=[CITY_CODE_VALIDATOR])
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    opening_date = models.DateField(null=True, blank=True)
    closing_date = models.DateField(null=True, blank=True)

    class Meta(OrganizationUnit.Meta):
        constraints = [
            *OrganizationUnit.Meta.constraints,
            status_check("restaurant", RestaurantStatus),
            models.CheckConstraint(
                condition=models.Q(closing_date__isnull=True)
                | models.Q(opening_date__isnull=True)
                | models.Q(closing_date__gte=models.F("opening_date")),
                name="org_restaurant_dates",
            ),
            models.CheckConstraint(
                condition=models.Q(latitude__isnull=True)
                | models.Q(latitude__gte=Decimal("-90"), latitude__lte=Decimal("90")),
                name="org_restaurant_latitude",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__isnull=True)
                | models.Q(longitude__gte=Decimal("-180"), longitude__lte=Decimal("180")),
                name="org_restaurant_longitude",
            ),
        ]
        indexes = [models.Index(fields=["city_code"], name="org_restaurant_city_idx")]

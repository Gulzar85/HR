"""django-filter FilterSets for organization lists (search, status, parent filters).

Parent choices are limited to the requesting user's scope; the list queryset itself is already
scope-filtered, so filters can never widen access.
"""

from __future__ import annotations

import django_filters as df
from django.db.models import Q

from .hierarchy import ORG_TYPES
from .models import (
    Area,
    Company,
    CorporateLocation,
    Department,
    Division,
    OrgStatus,
    Region,
    Restaurant,
    RestaurantStatus,
    StructureType,
)
from .selectors import visible_units


class OrgFilterSet(df.FilterSet):
    q = df.CharFilter(method="search", label="Search")
    status = df.ChoiceFilter(choices=OrgStatus.choices, label="Status")
    ordering = df.OrderingFilter(
        fields=(
            ("code", "code"),
            ("name", "name"),
            ("status", "status"),
            ("effective_from", "effective_from"),
        )
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, request=request, **kwargs)
        user = getattr(request, "user", None)
        for name, flt in self.filters.items():
            if name in ORG_TYPES and isinstance(flt, df.ModelChoiceFilter):
                flt.queryset = visible_units(user, name)

    @staticmethod
    def search(queryset, name, value):
        value = (value or "").strip()
        if not value:
            return queryset
        return queryset.filter(Q(code__icontains=value) | Q(name__icontains=value))


class CompanyFilter(OrgFilterSet):
    class Meta:
        model = Company
        fields: list[str] = []


class DivisionFilter(OrgFilterSet):
    company = df.ModelChoiceFilter(queryset=Company.objects.none(), label="Company")
    structure_type = df.ChoiceFilter(choices=StructureType.choices, label="Structure")

    class Meta:
        model = Division
        fields: list[str] = []


class CorporateLocationFilter(OrgFilterSet):
    division = df.ModelChoiceFilter(queryset=Division.objects.none(), label="Division")

    class Meta:
        model = CorporateLocation
        fields: list[str] = []


class DepartmentFilter(OrgFilterSet):
    corporate_location = df.ModelChoiceFilter(
        queryset=CorporateLocation.objects.none(), field_name="location", label="Corporate location"
    )

    class Meta:
        model = Department
        fields: list[str] = []


class RegionFilter(OrgFilterSet):
    class Meta:
        model = Region
        fields: list[str] = []


class AreaFilter(OrgFilterSet):
    region = df.ModelChoiceFilter(queryset=Region.objects.none(), label="Region")

    class Meta:
        model = Area
        fields: list[str] = []


class RestaurantFilter(OrgFilterSet):
    status = df.ChoiceFilter(choices=RestaurantStatus.choices, label="Status")
    region = df.ModelChoiceFilter(
        queryset=Region.objects.none(), field_name="area__region", label="Region"
    )
    area = df.ModelChoiceFilter(queryset=Area.objects.none(), label="Area")
    city_code = df.CharFilter(lookup_expr="iexact", label="City code")
    opening_date = df.DateFromToRangeFilter(label="Opening date")

    class Meta:
        model = Restaurant
        fields: list[str] = []


FILTERS = {
    "company": CompanyFilter,
    "division": DivisionFilter,
    "corporate_location": CorporateLocationFilter,
    "department": DepartmentFilter,
    "region": RegionFilter,
    "area": AreaFilter,
    "restaurant": RestaurantFilter,
}

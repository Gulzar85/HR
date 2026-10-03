"""Idempotent development/test seed for the locked organization hierarchy.

Creates (if missing): one company, Corporate + Operations divisions, Lahore + Karachi corporate
locations, five departments per location. ``sample_operations=True`` also creates example regions,
areas and restaurants (names are examples only; real data is maintained in the UI/imports).
Never runs automatically from migrations.
"""

from __future__ import annotations

from typing import Any

from .models import (
    Area,
    Company,
    CorporateLocation,
    Department,
    Division,
    Region,
    Restaurant,
    StructureType,
)
from .services import (
    AreaService,
    CompanyService,
    CorporateLocationService,
    DepartmentService,
    DivisionService,
    RegionService,
    RestaurantService,
)

DEPARTMENTS = [
    ("Finance", "FIN"),
    ("HR", "HR"),
    ("IT", "IT"),
    ("Supply Chain", "SCM"),
    ("Corporate Operations", "COPS"),
]
LOCATIONS = [("Lahore", "LHR"), ("Karachi", "KHI")]
SAMPLE_OPERATIONS = {
    "North Region": {"Lahore Central": ("LHR", 3), "Lahore North": ("LHR", 2)},
    "South Region": {"Karachi South": ("KHI", 3), "Karachi East": ("KHI", 2)},
}


def _get_or_create(model, service, parent_field, parent, name, data, stats, status=None):
    filters: dict[str, Any] = {"name__iexact": name}
    if parent_field:
        filters[parent_field] = parent
    existing = model.objects.filter(**filters).first()
    if existing:
        return existing
    stats["created"] += 1
    return service.create(
        actor=None, parent=parent, data={"name": name, **data}, status=status, reason="seed"
    )


def seed_organization(
    company_name: str = "McDonald's Pakistan", *, sample_operations: bool = False
) -> dict[str, int]:
    stats = {"created": 0}
    company = _get_or_create(
        Company, CompanyService, None, None, company_name,
        {"legal_name": "Siza Foods (Private) Limited", "description": "Seeded development company."},
        stats,
    )  # fmt: skip
    corporate = _get_or_create(
        Division, DivisionService, "company", company, "Corporate",
        {"structure_type": StructureType.CORPORATE}, stats,
    )  # fmt: skip
    operations = _get_or_create(
        Division, DivisionService, "company", company, "Operations",
        {"structure_type": StructureType.OPERATIONS}, stats,
    )  # fmt: skip
    for city, city_code in LOCATIONS:
        location = _get_or_create(
            CorporateLocation, CorporateLocationService, "division", corporate, city,
            {"city": city, "city_code": city_code}, stats,
        )  # fmt: skip
        for dept, short in DEPARTMENTS:
            _get_or_create(
                Department,
                DepartmentService,
                "location",
                location,
                dept,
                {"short_code": short},
                stats,
            )
    if sample_operations:
        for region_name, areas in SAMPLE_OPERATIONS.items():
            region = _get_or_create(
                Region, RegionService, "division", operations, region_name, {}, stats
            )
            for area_name, (city_code, count) in areas.items():
                area = _get_or_create(Area, AreaService, "region", region, area_name, {}, stats)
                for i in range(1, count + 1):
                    _get_or_create(
                        Restaurant, RestaurantService, "area", area, f"{area_name} {i}",
                        {"city_code": city_code, "city": area_name.split()[0], "short_name": f"{area_name[:3]}{i}"},
                        stats, status="active",
                    )  # fmt: skip
    return stats

"""Hierarchy, codes, validation, uniqueness, permissions and history of create/update."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.audit.models import AuditLog
from apps.common.exceptions import (
    BusinessRuleException,
    ConflictException,
    PermissionDeniedException,
    ValidationException,
)
from apps.organizations.hierarchy import ancestors_of, assert_not_own_ancestor, scope_lookups
from apps.organizations.models import (
    Company,
    Department,
    OrganizationHistory,
    OrganizationRelationship,
    Restaurant,
    StructureType,
)
from apps.organizations.services import (
    AreaService,
    CompanyService,
    CorporateLocationService,
    DepartmentService,
    DivisionService,
    OrganizationService,
    RegionService,
    RestaurantService,
)

pytestmark = pytest.mark.django_db


def test_seed_builds_the_locked_hierarchy(org):
    assert org.company.code == "CMP-001"
    assert {org.corporate.code, org.operations.code} == {"DIV-CORP-001", "DIV-OPS-001"}
    assert {org.lahore.code, org.karachi.code} == {"LOC-LHR-001", "LOC-KHI-001"}
    for loc in (org.lahore, org.karachi):
        assert set(loc.departments.values_list("name", flat=True)) == {
            "Finance", "HR", "IT", "Supply Chain", "Corporate Operations"
        }  # fmt: skip
    assert (
        Department.objects.filter(code__in=["DEPT-LHR-HR", "DEPT-KHI-HR"]).count() == 2
    )  # HR is per location
    assert org.north.code.startswith("REG-") and org.lhr_central.code.startswith("AREA-")
    assert org.rst_north.code.startswith("RST-LHR-") and org.rst_south.code.startswith("RST-KHI-")
    assert [a.ORG_TYPE for a in ancestors_of(org.rst_north)] == [
        "area",
        "region",
        "division",
        "company",
    ]


def test_codes_are_generated_and_immutable(org, org_admin):
    region = RegionService.create(
        actor=org_admin, parent=org.operations, data={"name": "Central Region"}
    )
    assert region.code.startswith("REG-") and len(region.code) == 7
    region.code = "REG-999"
    with pytest.raises(ValidationError):
        region.save()


def test_every_create_writes_history_relationship_and_audit(org, org_admin):
    area = AreaService.create(
        actor=org_admin, parent=org.north, data={"name": "Gulberg"}, reason="expansion"
    )
    assert OrganizationHistory.objects.filter(
        entity_id=area.pk, event="created", reason="expansion"
    ).exists()
    rel = OrganizationRelationship.objects.get(child_id=area.pk)
    assert rel.parent_id == org.north.pk and rel.effective_to is None
    assert AuditLog.objects.filter(
        action="organizations.area_created", object_id=str(area.pk), actor=org_admin
    ).exists()


@pytest.mark.parametrize(
    ("service", "parent_attr", "data"),
    [
        (RegionService, "corporate", {"name": "Wrong"}),  # region under a CORPORATE division
        (
            CorporateLocationService,
            "operations",
            {"name": "Wrong", "city_code": "ISB"},
        ),  # location under OPERATIONS
        (AreaService, "lahore", {"name": "Wrong"}),  # area under a corporate location
        (
            RestaurantService,
            "lhr_hr",
            {"name": "Wrong", "city_code": "LHR"},
        ),  # restaurant under a department
        (
            RestaurantService,
            "north",
            {"name": "Wrong", "city_code": "LHR"},
        ),  # restaurant directly under a region
        (
            DepartmentService,
            "operations",
            {"name": "Wrong", "short_code": "XX"},
        ),  # department under division
        (DivisionService, "lahore", {"name": "Wrong", "structure_type": "corporate"}),
    ],
)
def test_invalid_parents_are_rejected(org, org_admin, service, parent_attr, data):
    with pytest.raises(BusinessRuleException) as exc:
        service.create(actor=org_admin, parent=getattr(org, parent_attr), data=data)
    assert exc.value.code == "invalid_hierarchy"


def test_missing_parent_is_rejected(org_admin, db):
    with pytest.raises(BusinessRuleException):
        RestaurantService.create(
            actor=org_admin, parent=None, data={"name": "Orphan", "city_code": "LHR"}
        )


def test_company_has_no_parent_and_supports_multiple_companies(org, org_admin):
    other = CompanyService.create(actor=org_admin, data={"name": "Second Co"})
    assert other.code == "CMP-002"
    assert Company.objects.count() == 2
    with pytest.raises(BusinessRuleException):
        CompanyService.create(actor=org_admin, parent=org.company, data={"name": "Child Co"})


def test_name_uniqueness_within_parent_only(org, org_admin):
    with pytest.raises(ConflictException):
        AreaService.create(actor=org_admin, parent=org.north, data={"name": "lahore central"})
    # the same name under another region is fine
    AreaService.create(actor=org_admin, parent=org.south, data={"name": "Lahore Central"})


def test_department_short_code_unique_per_location(org, org_admin):
    with pytest.raises(ConflictException):
        DepartmentService.create(
            actor=org_admin, parent=org.lahore, data={"name": "Human Resources", "short_code": "HR"}
        )
    with pytest.raises(
        ConflictException
    ):  # code DEPT-LHR-HR already exists even if the name differs
        DepartmentService.create(
            actor=org_admin, parent=org.lahore, data={"name": "People", "short_code": "HR"}
        )


def test_field_validation_becomes_validation_exception(org, org_admin):
    with pytest.raises(ValidationException) as exc:
        RestaurantService.create(
            actor=org_admin, parent=org.lhr_central, data={"name": "Bad", "city_code": "lahore"}
        )
    assert "city_code" in exc.value.details


def test_restaurant_database_constraints(org):
    r = org.rst_north
    r.latitude = 123
    with pytest.raises(Exception):  # noqa: B017  check constraint (IntegrityError)
        r.save()


def test_active_child_cannot_be_created_under_planned_parent(org, org_admin):
    planned = AreaService.create(
        actor=org_admin, parent=org.north, data={"name": "Future"}, status="planned"
    )
    with pytest.raises(BusinessRuleException):
        RestaurantService.create(
            actor=org_admin, parent=planned, data={"name": "X", "city_code": "LHR"}, status="active"
        )
    RestaurantService.create(
        actor=org_admin, parent=planned, data={"name": "Y", "city_code": "LHR"}
    )  # planned is fine


def test_update_records_rename_and_diff(org, org_admin):
    OrganizationService.update(
        org.north, actor=org_admin, data={"name": "Punjab Region"}, reason="rebrand"
    )
    h = OrganizationHistory.objects.get(entity_id=org.north.pk, event="renamed")
    assert h.before == {"name": "North Region"} and h.after == {"name": "Punjab Region"}
    OrganizationService.update(org.north, actor=org_admin, data={"description": "x"})
    assert OrganizationHistory.objects.filter(entity_id=org.north.pk, event="updated").exists()
    # no-op updates write nothing
    before = OrganizationHistory.objects.count()
    OrganizationService.update(org.north, actor=org_admin, data={"description": "x"})
    assert OrganizationHistory.objects.count() == before


def test_permissions_are_required(org, make_user, scoped):
    nobody = make_user("nobody@example.com")
    with pytest.raises(PermissionDeniedException):
        RegionService.create(actor=nobody, parent=org.operations, data={"name": "Hack"})
    viewer = scoped("global", perms=["organizations.view_region"], email="viewer@example.com")
    with pytest.raises(PermissionDeniedException):
        RegionService.create(actor=viewer, parent=org.operations, data={"name": "Hack"})
    with pytest.raises(PermissionDeniedException):
        OrganizationService.update(org.north, actor=viewer, data={"name": "Hack"})


def test_creation_requires_scope_on_the_parent(org, scoped):
    south_manager = scoped("region", org.south, email="south@example.com")
    with pytest.raises(PermissionDeniedException):
        AreaService.create(actor=south_manager, parent=org.north, data={"name": "Sneaky"})
    AreaService.create(actor=south_manager, parent=org.south, data={"name": "Allowed"})
    with pytest.raises(PermissionDeniedException):  # companies need organization-wide scope
        CompanyService.create(actor=south_manager, data={"name": "Rogue Co"})


def test_circular_hierarchy_guard(org):
    with pytest.raises(BusinessRuleException) as exc:
        assert_not_own_ancestor(org.north, org.lhr_central)  # region under its own area
    assert exc.value.code == "circular_hierarchy"
    assert_not_own_ancestor(org.lhr_central, org.south)  # unrelated: fine


def test_scope_lookups_for_future_domains():
    assert scope_lookups("restaurant") == {
        "restaurant": "id", "area": "area_id", "region": "area__region_id",
        "division": "area__region__division_id", "company": "area__region__division__company_id",
    }  # fmt: skip
    assert scope_lookups("department", "assignment__department")["corporate_location"] == (
        "assignment__department__location_id"
    )


def test_structure_type_is_data_not_code(org, org_admin):
    """Division names are configurable; behaviour follows structure_type."""
    renamed = OrganizationService.update(
        org.operations, actor=org_admin, data={"name": "Restaurants Division"}
    )
    region = RegionService.create(actor=org_admin, parent=renamed, data={"name": "West"})
    assert region.division.structure_type == StructureType.OPERATIONS
    assert Restaurant.objects.count() == 10

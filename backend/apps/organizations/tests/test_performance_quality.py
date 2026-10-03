"""Query-count guarantees on a realistic dataset, data-quality checks and management commands."""

from __future__ import annotations

import io
from datetime import date

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from apps.data_quality.registry import run_checks
from apps.organizations.models import (
    Area,
    Company,
    CorporateLocation,
    Department,
    Division,
    OrganizationRelationship,
    Region,
    Restaurant,
    StructureType,
)
from apps.organizations.seed import seed_organization
from apps.organizations.selectors import get_organization_tree

from .conftest import ORG_VIEW_PERMS, grant

pytestmark = pytest.mark.django_db


@pytest.fixture
def big_org(db):
    """1 company, 2 divisions, 2 locations, 10 departments, 10 regions, 50 areas, 500 restaurants.
    Bulk-inserted directly (fixture data, not a business operation)."""
    d0 = date(2024, 1, 1)
    company = Company.objects.create(code="CMP-900", name="Perf Co", effective_from=d0)
    corp = Division.objects.create(
        code="DIV-CORP-900",
        name="Corporate",
        company=company,
        structure_type=StructureType.CORPORATE,
        effective_from=d0,
    )
    ops = Division.objects.create(
        code="DIV-OPS-900",
        name="Operations",
        company=company,
        structure_type=StructureType.OPERATIONS,
        effective_from=d0,
    )
    locs = [
        CorporateLocation.objects.create(
            code=f"LOC-P{i}-900", name=f"Loc {i}", city_code="LHR", division=corp, effective_from=d0
        )
        for i in range(2)
    ]
    Department.objects.bulk_create(
        [
            Department(
                code=f"DEPT-P{i}-D{j}",
                name=f"Dept {j}",
                short_code=f"D{j}",
                location=loc,
                effective_from=d0,
            )
            for i, loc in enumerate(locs)
            for j in range(5)
        ]
    )
    regions = Region.objects.bulk_create(
        [
            Region(code=f"REG-9{i:02d}", name=f"Region {i}", division=ops, effective_from=d0)
            for i in range(10)
        ]
    )
    areas = Area.objects.bulk_create(
        [
            Area(code=f"AREA-9{r:02d}{a}", name=f"Area {r}-{a}", region=reg, effective_from=d0)
            for r, reg in enumerate(regions)
            for a in range(5)
        ]
    )
    Restaurant.objects.bulk_create(
        [
            Restaurant(
                code=f"RST-LHR-9{n:03d}{k}",
                name=f"Store {n}-{k}",
                city_code="LHR",
                area=area,
                status="active",
                effective_from=d0,
            )
            for n, area in enumerate(areas)
            for k in range(10)
        ]
    )
    return {"company": company, "regions": regions, "areas": areas}


def test_tree_is_constant_queries_for_500_restaurants(big_org, django_assert_max_num_queries):
    assert Restaurant.objects.count() == 500
    with django_assert_max_num_queries(7):
        tree = get_organization_tree()
    ops = next(n for n in tree[0]["children"] if n["code"] == "DIV-OPS-900")
    assert ops["counts"]["restaurant"] == 500 and ops["counts"]["area"] == 50


def test_scoped_tree_is_bounded(big_org, make_user, django_assert_max_num_queries):
    user = make_user()
    grant(user, "region", big_org["regions"][3])
    with django_assert_max_num_queries(25):
        tree = get_organization_tree(user)
    region_nodes = (
        tree[0]["children"][0]["children"]
        if tree[0]["children"][0]["code"] == "DIV-OPS-900"
        else tree[0]["children"][1]["children"]
    )
    assert [n["code"] for n in region_nodes] == ["REG-903"]


def test_restaurant_list_page_queries_do_not_grow(
    big_org, client, make_user, django_assert_max_num_queries
):
    user = make_user(perms=ORG_VIEW_PERMS + ["organizations.view_restaurant"])
    grant(user, "global")
    client.force_login(user)
    with django_assert_max_num_queries(20):
        r = client.get(reverse("organizations:restaurant_list"))
    assert r.status_code == 200 and r.context["page_obj"].paginator.count == 500


def test_tree_page_renders_large_dataset(big_org, client, make_user, django_assert_max_num_queries):
    user = make_user(perms=ORG_VIEW_PERMS)
    grant(user, "global")
    client.force_login(user)
    with django_assert_max_num_queries(20):
        assert client.get(reverse("organizations:tree")).status_code == 200


# ---------------------------------------------------------------------------- data quality
def test_clean_seed_has_no_issues(org):
    assert [i for i in run_checks("organizations") if i.severity == "error"] == []


def test_checks_detect_data_loaded_around_services(org, big_org):
    issues = run_checks("organizations")
    codes = {i.check for i in issues}
    assert "ORG-NO-RELATIONSHIP" in codes  # bulk-loaded units have no relationship rows
    # inactive parent with live child (bypassing the service)
    Area.objects.filter(pk=org.lhr_central.pk).update(status="inactive")
    assert any(
        i.check == "ORG-INACTIVE-PARENT" and i.object_code.startswith("RST-")
        for i in run_checks("organizations")
    )


def test_overlapping_and_mismatched_relationships_detected(org):
    OrganizationRelationship.objects.create(
        child_type="restaurant", child_id=org.rst_north.pk, parent_type="area", parent_id=org.lhr_north.pk,
        effective_from=date(2020, 1, 1), effective_to=date(2099, 1, 1),
    )  # fmt: skip
    Restaurant.objects.filter(pk=org.rst_south.pk).update(
        area=org.lhr_central
    )  # FK changed without a move
    codes = {i.check for i in run_checks("organizations")}
    assert {"ORG-OVERLAPPING-RELATIONSHIPS", "ORG-RELATIONSHIP-MISMATCH"} <= codes


def test_invalid_hierarchy_detected(org):
    Region.objects.filter(pk=org.north.pk).update(division=org.corporate)  # region under CORPORATE
    assert any(i.check == "ORG-INVALID-HIERARCHY" for i in run_checks("organizations"))


# --------------------------------------------------------------------------- commands
def test_seed_command_is_idempotent_and_guarded(db, settings):
    settings.DEBUG = True
    out = io.StringIO()
    call_command("seed_organization", stdout=out)
    assert "created" in out.getvalue()
    first = Department.objects.count()
    call_command("seed_organization", stdout=io.StringIO())
    assert Department.objects.count() == first == 10
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_organization", stdout=io.StringIO())


def test_validate_and_tree_commands(org):
    out = io.StringIO()
    call_command("validate_organization", stdout=out)
    assert "OK" in out.getvalue()
    out = io.StringIO()
    call_command("organization_tree", stdout=out)
    assert "DEPT-LHR-HR" in out.getvalue() and org.rst_north.code in out.getvalue()
    Area.objects.filter(pk=org.lhr_central.pk).update(status="inactive")
    with pytest.raises(CommandError):
        call_command("validate_organization", stdout=io.StringIO())


def test_seed_never_runs_from_migrations(db):
    assert Company.objects.count() == 0  # a migrated, unseeded database has no organization data
    seed_organization()
    assert Company.objects.count() == 1

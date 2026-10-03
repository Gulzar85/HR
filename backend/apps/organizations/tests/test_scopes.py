"""Phase 1 UserScope working with real organization units: inheritance, filtering, normalisation."""

from __future__ import annotations

import pytest

from apps.accounts.models import UserScope
from apps.accounts.services import ScopeService
from apps.common.exceptions import ValidationException
from apps.organizations.models import (
    Area,
    CorporateLocation,
    Department,
    Division,
    Region,
    Restaurant,
)
from apps.organizations.services import OrganizationScopeService

from .conftest import grant

pytestmark = pytest.mark.django_db


def visible(user, key):
    return set(OrganizationScopeService.visible(user, key).values_list("pk", flat=True))


def test_company_scope_covers_everything(org, make_user):
    u = make_user()
    grant(u, "company", org.company)
    assert visible(u, "restaurant") == set(Restaurant.objects.values_list("pk", flat=True))
    assert visible(u, "department") == set(Department.objects.values_list("pk", flat=True))
    assert ScopeService.user_can_access_organization(u, "company", str(org.company.pk))


def test_division_scope(org, make_user):
    u = make_user()
    grant(u, "division", org.operations)
    assert visible(u, "restaurant") == set(Restaurant.objects.values_list("pk", flat=True))
    assert visible(u, "department") == set()  # corporate side is outside an Operations scope
    assert visible(u, "division") == {org.operations.pk}


def test_corporate_location_scope(org, make_user):
    u = make_user()
    grant(u, "corporate_location", org.lahore)
    assert visible(u, "department") == set(org.lahore.departments.values_list("pk", flat=True))
    assert not ScopeService.user_can_access_organization(
        u, "department", str(Department.objects.get(code="DEPT-KHI-HR").pk)
    )
    assert visible(u, "restaurant") == set()


def test_department_scope(org, make_user):
    u = make_user()
    grant(u, "department", org.lhr_hr)
    assert visible(u, "department") == {org.lhr_hr.pk}
    assert visible(u, "corporate_location") == set()  # scope does not grant the parent


def test_region_scope_inherits_areas_and_restaurants_only_in_that_region(org, make_user):
    u = make_user()
    grant(u, "region", org.north)
    north_restaurants = set(
        Restaurant.objects.filter(area__region=org.north).values_list("pk", flat=True)
    )
    assert visible(u, "restaurant") == north_restaurants and north_restaurants
    assert visible(u, "area") == set(
        Area.objects.filter(region=org.north).values_list("pk", flat=True)
    )
    assert ScopeService.user_can_access_organization(u, "restaurant", str(org.rst_north.pk))
    assert not ScopeService.user_can_access_organization(u, "restaurant", str(org.rst_south.pk))
    assert not ScopeService.user_can_access_organization(u, "region", str(org.south.pk))


def test_area_scope(org, make_user):
    u = make_user()
    grant(u, "area", org.lhr_central)
    assert visible(u, "restaurant") == set(org.lhr_central.restaurants.values_list("pk", flat=True))
    assert visible(u, "region") == set()


def test_restaurant_scope(org, make_user):
    u = make_user()
    grant(u, "restaurant", org.rst_north)
    assert visible(u, "restaurant") == {org.rst_north.pk}
    assert visible(u, "area") == set()


def test_scope_without_descendants_covers_only_the_unit(org, make_user):
    u = make_user()
    grant(u, "region", org.north, descendants=False)
    assert visible(u, "region") == {org.north.pk}
    assert visible(u, "restaurant") == set()
    assert not ScopeService.user_can_access_organization(u, "area", str(org.lhr_central.pk))


def test_global_and_superuser_see_all_and_no_scope_sees_nothing(org, make_user):
    g = make_user()
    grant(g, "global")
    assert len(visible(g, "restaurant")) == Restaurant.objects.count()
    su = make_user(superuser=True)
    assert len(visible(su, "region")) == Region.objects.count()
    nobody = make_user()
    assert visible(nobody, "restaurant") == set() and visible(nobody, "company") == set()


def test_multiple_scopes_combine(org, make_user):
    u = make_user()
    grant(u, "restaurant", org.rst_north)
    grant(u, "area", org.khi_south)
    expected = {org.rst_north.pk, *org.khi_south.restaurants.values_list("pk", flat=True)}
    assert visible(u, "restaurant") == expected


def test_new_units_are_covered_automatically(org, org_admin, make_user):
    from apps.organizations.services import RestaurantService

    u = make_user()
    grant(u, "region", org.north)
    new = RestaurantService.create(
        actor=org_admin, parent=org.lhr_north, data={"name": "Brand New", "city_code": "LHR"}
    )
    assert new.pk in visible(u, "restaurant")  # resolved by joins, no re-granting needed


def test_moving_a_unit_changes_who_can_see_it(org, org_admin, make_user):
    from apps.organizations.services import RestaurantService

    u = make_user()
    grant(u, "area", org.lhr_central)
    RestaurantService.move(org.rst_north, org.khi_south, actor=org_admin, reason="x")
    assert org.rst_north.pk not in visible(u, "restaurant")


def test_grant_scope_by_code_normalises_to_uuid(org, org_admin, make_user):
    target = make_user()
    scope = ScopeService.grant_scope(
        actor=org_admin, user=target, scope_type="restaurant", scope_ref=org.rst_north.code.lower()
    )
    assert scope.scope_ref == str(org.rst_north.pk)
    with pytest.raises(ValidationException):
        ScopeService.grant_scope(
            actor=org_admin, user=target, scope_type="restaurant", scope_ref="RST-NOPE-999"
        )
    with pytest.raises(ValidationException):  # a region code is not a restaurant
        ScopeService.grant_scope(
            actor=org_admin, user=target, scope_type="restaurant", scope_ref=org.north.code
        )
    rows = ScopeService.resolve_user_organization_scopes(target)
    assert (
        rows[0]["display"] == f"{org.rst_north.code} · {org.rst_north.name}"
        and rows[0]["type_label"] == "Restaurant"
    )


def test_scoped_manager_can_only_grant_within_own_scope(org, scoped, make_user):
    north = scoped("region", org.north, perms=["accounts.manage_users"], email="rm@example.com")
    staff = make_user()
    ScopeService.grant_scope(
        actor=north, user=staff, scope_type="restaurant", scope_ref=str(org.rst_north.pk)
    )
    with pytest.raises(Exception):  # noqa: B017  PermissionDenied: outside own scope
        ScopeService.grant_scope(
            actor=north, user=staff, scope_type="restaurant", scope_ref=str(org.rst_south.pk)
        )


def test_filter_queryset_for_future_domains_with_prefix(org, make_user):
    """Simulates an Assignment-like queryset that points to an Area: Restaurant rows via 'area'."""
    u = make_user()
    grant(u, "region", org.north)
    qs = OrganizationScopeService.filter_queryset(
        u, Restaurant.objects.all(), "area", prefix="area"
    )
    assert set(qs.values_list("pk", flat=True)) == set(
        Restaurant.objects.filter(area__region=org.north).values_list("pk", flat=True)
    )


def test_ancestors_and_descendants_helpers(org):
    anc = ScopeService.get_ancestors("restaurant", str(org.rst_north.pk))
    assert ("region", str(org.north.pk)) in anc and ("company", str(org.company.pk)) in anc
    desc = ScopeService.get_descendants("corporate_location", str(org.lahore.pk))
    assert len(desc) == 5 and all(t == "department" for t, _ in desc)
    assert ScopeService.get_descendants("region", "not-a-uuid") == []


def test_stale_scope_reference_grants_nothing(org, make_user):
    u = make_user()
    UserScope.objects.create(
        user=u, scope_type="region", scope_ref="00000000-0000-0000-0000-000000000000"
    )
    assert visible(u, "restaurant") == set()
    assert ScopeService.describe("region", "00000000-0000-0000-0000-000000000000").endswith(
        "(unknown)"
    )


def test_location_and_division_listing_respect_scope(org, make_user):
    u = make_user()
    grant(u, "corporate_location", org.karachi)
    assert visible(u, "corporate_location") == {org.karachi.pk}
    assert visible(u, "division") == set()
    assert CorporateLocation.objects.count() == 2 and Division.objects.count() == 2

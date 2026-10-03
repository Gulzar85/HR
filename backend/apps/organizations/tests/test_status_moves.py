"""Status lifecycles, parent/child integrity, moves, effective-dated history and atomicity."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from apps.common.exceptions import (
    BusinessRuleException,
    ConflictException,
    PermissionDeniedException,
)
from apps.common.utils import today_local
from apps.organizations.models import (
    Department,
    OrganizationHistory,
    OrganizationRelationship,
    Restaurant,
)
from apps.organizations.selectors import ancestor_of_type_on, ancestors_on, parent_on
from apps.organizations.services import (
    AreaService,
    CompanyService,
    DepartmentService,
    OrganizationService,
    RestaurantService,
)

pytestmark = pytest.mark.django_db


def _new_restaurant(org, actor, **kw):
    return RestaurantService.create(
        actor=actor,
        parent=org.lhr_central,
        data={"name": kw.pop("name", "New Store"), "city_code": "LHR", **kw},
    )


def test_restaurant_lifecycle(org, org_admin):
    r = _new_restaurant(org, org_admin)
    assert r.status == "planned" and r.opening_date is None
    r = RestaurantService.change_status(r, "activate", actor=org_admin, reason="grand opening")
    assert r.status == "active" and r.opening_date == today_local()
    r = RestaurantService.change_status(
        r, "temporarily_close", actor=org_admin, reason="renovation"
    )
    assert r.status == "temporarily_closed" and r.is_live
    r = RestaurantService.change_status(r, "reopen", actor=org_admin, reason="done")
    assert r.status == "active"
    r = RestaurantService.change_status(r, "close", actor=org_admin, reason="lease ended")
    assert (
        r.status == "closed" and r.closing_date == today_local() and r.effective_to == today_local()
    )
    r = RestaurantService.change_status(r, "reopen", actor=org_admin, reason="lease renewed")
    assert r.status == "active" and r.closing_date is None and r.effective_to is None
    events = list(
        OrganizationHistory.objects.filter(entity_id=r.pk).values_list("event", flat=True)
    )
    assert {"created", "activated", "temporarily_closed", "reopened", "closed"} <= set(events)


def test_invalid_restaurant_transitions(org, org_admin):
    r = _new_restaurant(org, org_admin)
    with pytest.raises(BusinessRuleException):
        RestaurantService.change_status(
            r, "close", actor=org_admin, reason="x"
        )  # planned cannot close
    with pytest.raises(BusinessRuleException):
        RestaurantService.change_status(r, "reopen", actor=org_admin, reason="x")
    RestaurantService.change_status(r, "archive", actor=org_admin, reason="plan cancelled")
    r.refresh_from_db()
    assert r.status == "archived"


def test_generic_status_and_child_integrity(org, org_admin):
    with pytest.raises(BusinessRuleException) as exc:
        OrganizationService.change_status(
            org.lhr_central, "deactivate", actor=org_admin, reason="x"
        )
    assert exc.value.code == "active_children"
    for r in org.lhr_central.restaurants.all():
        RestaurantService.change_status(r, "close", actor=org_admin, reason="area closing")
    area = OrganizationService.change_status(
        org.lhr_central, "deactivate", actor=org_admin, reason="merged"
    )
    assert area.status == "inactive" and area.effective_to == today_local()
    # a closed restaurant cannot reopen while its area is inactive
    with pytest.raises(BusinessRuleException) as exc:
        RestaurantService.change_status(
            org.lhr_central.restaurants.first(), "reopen", actor=org_admin, reason="x"
        )
    assert exc.value.code == "inactive_parent"
    area = OrganizationService.change_status(area, "activate", actor=org_admin, reason="back")
    assert area.status == "active" and area.effective_to is None
    OrganizationService.change_status(area, "deactivate", actor=org_admin, reason="x")
    area = OrganizationService.change_status(area, "archive", actor=org_admin, reason="x")
    assert area.status == "archived"


def test_cannot_add_children_to_inactive_unit(org, org_admin):
    dept = DepartmentService.create(
        actor=org_admin, parent=org.lahore, data={"name": "Legal", "short_code": "LEG"}
    )
    OrganizationService.change_status(dept, "deactivate", actor=org_admin, reason="x")
    for d in Department.objects.filter(location=org.karachi):
        OrganizationService.change_status(d, "deactivate", actor=org_admin, reason="x")
    OrganizationService.change_status(
        org.karachi, "deactivate", actor=org_admin, reason="office closed"
    )
    with pytest.raises(BusinessRuleException):
        DepartmentService.create(
            actor=org_admin, parent=org.karachi, data={"name": "Legal", "short_code": "LEG"}
        )


def test_status_change_requires_permission_and_scope(org, scoped, make_user):
    viewer = scoped("global", perms=["organizations.view_restaurant"], email="v@example.com")
    with pytest.raises(PermissionDeniedException):
        RestaurantService.change_status(org.rst_north, "close", actor=viewer, reason="x")
    south = scoped("region", org.south, email="s@example.com")
    with pytest.raises(
        PermissionDeniedException
    ):  # unauthorized restaurant closure in another region
        RestaurantService.change_status(org.rst_north, "close", actor=south, reason="x")
    RestaurantService.change_status(org.rst_south, "temporarily_close", actor=south, reason="ok")


def test_effective_date_cannot_precede_start(org, org_admin):
    with pytest.raises(BusinessRuleException):
        RestaurantService.change_status(
            org.rst_north, "close", actor=org_admin, reason="x", effective_date=date(2000, 1, 1)
        )


def test_move_restaurant_preserves_history(org, org_admin):
    r = org.rst_north
    moved_on = today_local() + timedelta(days=10)
    RestaurantService.move(
        r, org.lhr_north, actor=org_admin, reason="re-zoning", effective_date=moved_on
    )
    r.refresh_from_db()
    assert r.area == org.lhr_north
    rels = list(OrganizationRelationship.objects.filter(child_id=r.pk).order_by("effective_from"))
    assert len(rels) == 2
    assert rels[0].parent_id == org.lhr_central.pk and rels[0].effective_to == moved_on
    assert rels[1].parent_id == org.lhr_north.pk and rels[1].effective_to is None
    # historical questions
    assert parent_on("restaurant", r.pk, today_local()) == ("area", org.lhr_central.pk)
    assert parent_on("restaurant", r.pk, moved_on) == ("area", org.lhr_north.pk)
    assert ancestor_of_type_on(r, "area", today_local()) == org.lhr_central
    h = OrganizationHistory.objects.get(entity_id=r.pk, event="moved")
    assert h.before == {"parent": org.lhr_central.code} and h.reason == "re-zoning"


def test_which_region_did_a_restaurant_belong_to(org, org_admin):
    """Area moves to another region; the restaurant's historical region is still answerable."""
    r = org.rst_north
    move_date = today_local() + timedelta(days=30)
    AreaService.move(
        org.lhr_central, org.south, actor=org_admin, reason="restructure", effective_date=move_date
    )
    assert ancestor_of_type_on(r, "region", today_local()) == org.north
    assert ancestor_of_type_on(r, "region", move_date) == org.south
    assert [u.ORG_TYPE for u in ancestors_on(r, move_date)] == [
        "area",
        "region",
        "division",
        "company",
    ]


def test_invalid_moves(org, org_admin):
    with pytest.raises(BusinessRuleException):
        RestaurantService.move(
            org.rst_north, org.lhr_central, actor=org_admin, reason="same parent"
        )
    with pytest.raises(BusinessRuleException):  # wrong parent type
        RestaurantService.move(org.rst_north, org.north, actor=org_admin, reason="x")
    with pytest.raises(BusinessRuleException):
        OrganizationService.move(org.company, org.operations, actor=org_admin, reason="x")
    with pytest.raises(BusinessRuleException):  # before current placement started
        RestaurantService.move(
            org.rst_north,
            org.lhr_north,
            actor=org_admin,
            reason="x",
            effective_date=date(2000, 1, 1),
        )
    planned = AreaService.create(
        actor=org_admin, parent=org.north, data={"name": "Planned"}, status="planned"
    )
    with pytest.raises(BusinessRuleException):  # active unit cannot go under a non-active parent
        RestaurantService.move(org.rst_north, planned, actor=org_admin, reason="x")


def test_cannot_move_across_companies(org, org_admin):
    from apps.organizations.models import StructureType
    from apps.organizations.services import DivisionService, RegionService

    other = CompanyService.create(actor=org_admin, data={"name": "Other Co"})
    ops = DivisionService.create(
        actor=org_admin,
        parent=other,
        data={"name": "Ops", "structure_type": StructureType.OPERATIONS},
    )
    region = RegionService.create(actor=org_admin, parent=ops, data={"name": "Elsewhere"})
    with pytest.raises(BusinessRuleException):
        AreaService.move(org.lhr_central, region, actor=org_admin, reason="x")


def test_department_move_checks_short_code_clash(org, org_admin):
    with pytest.raises(ConflictException):
        DepartmentService.move(
            org.lhr_hr, org.karachi, actor=org_admin, reason="x"
        )  # Karachi already has HR
    renamed = DepartmentService.create(
        actor=org_admin, parent=org.lahore, data={"name": "People Ops", "short_code": "PEO"}
    )
    DepartmentService.create(
        actor=org_admin, parent=org.karachi, data={"name": "Talent", "short_code": "PEO"}
    )
    with pytest.raises(ConflictException) as exc:
        DepartmentService.move(renamed, org.karachi, actor=org_admin, reason="x")
    assert "short code" in exc.value.message
    legal = DepartmentService.create(
        actor=org_admin, parent=org.lahore, data={"name": "Legal", "short_code": "LEG"}
    )
    moved = DepartmentService.move(legal, org.karachi, actor=org_admin, reason="relocated")
    assert moved.location == org.karachi and moved.code == "DEPT-LHR-LEG"  # codes are immutable


def test_moves_require_permission_and_scope_on_both_sides(org, scoped):
    south = scoped("region", org.south, email="south@example.com")
    with pytest.raises(PermissionDeniedException):  # unauthorized parent change into own region
        RestaurantService.move(org.rst_north, org.khi_south, actor=south, reason="grab")
    no_move = scoped(
        "global",
        perms=["organizations.view_restaurant", "organizations.change_restaurant"],
        email="nm@example.com",
    )
    with pytest.raises(PermissionDeniedException):
        RestaurantService.move(org.rst_north, org.lhr_north, actor=no_move, reason="x")


def test_failed_operation_leaves_no_partial_changes(org, org_admin, monkeypatch):
    from apps.organizations.services import organization_service

    def boom(*a, **k):
        raise RuntimeError("history store down")

    monkeypatch.setattr(organization_service, "record_history", boom)
    with pytest.raises(RuntimeError):
        RestaurantService.move(org.rst_north, org.lhr_north, actor=org_admin, reason="x")
    org.rst_north.refresh_from_db()
    assert org.rst_north.area == org.lhr_central
    assert OrganizationRelationship.objects.filter(child_id=org.rst_north.pk).count() == 1
    count = Restaurant.objects.count()
    with pytest.raises(RuntimeError):
        _new_restaurant(org, org_admin, name="Ghost")
    assert Restaurant.objects.count() == count


def test_restaurant_created_active_gets_opening_date(org, org_admin):
    r = RestaurantService.create(
        actor=org_admin,
        parent=org.lhr_central,
        data={"name": "Open Now", "city_code": "LHR"},
        status="active",
    )
    assert r.opening_date == r.effective_from

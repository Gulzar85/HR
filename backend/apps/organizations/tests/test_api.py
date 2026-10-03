"""Organization REST API: CRUD via services, scope enforcement, IDOR, tree, aliases."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.organizations.models import Restaurant

from .conftest import ORG_VIEW_PERMS

pytestmark = pytest.mark.django_db
V1 = "/api/v1"


def api(user) -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return c


def test_requires_authentication_and_permission(org, make_user):
    assert APIClient().get(f"{V1}/organizations/restaurants/").status_code == 401
    r = api(make_user("np@example.com")).get(f"{V1}/organizations/restaurants/")
    assert r.status_code == 403 and r.json()["error"]["code"] == "permission_denied"


def test_list_detail_pagination_and_filters(org, org_admin):
    c = api(org_admin)
    body = c.get(f"{V1}/organizations/restaurants/", {"page_size": 4}).json()
    assert body["count"] == 10 and len(body["results"]) == 4 and body["next"]
    first = body["results"][0]
    assert set(first) >= {"id", "code", "name", "status", "type", "parent", "city_code"}
    assert first["parent"]["type"] == "area"
    assert (
        c.get(f"{V1}/organizations/restaurants/", {"region": str(org.south.pk)}).json()["count"]
        == 5
    )
    assert c.get(f"{V1}/organizations/restaurants/", {"q": org.rst_north.code}).json()["count"] == 1
    r = c.get(f"{V1}/organizations/departments/", {"corporate_location": str(org.lahore.pk)})
    assert r.json()["count"] == 5
    detail = c.get(f"{V1}/organizations/regions/{org.north.pk}/").json()["data"]
    assert detail["code"] == org.north.code and detail["parent"]["code"] == org.operations.code


def test_region_scoped_user_cannot_reach_other_region_by_uuid(org, scoped):
    user = scoped("region", org.north, perms=ORG_VIEW_PERMS, email="rn@example.com")
    c = api(user)
    assert c.get(f"{V1}/restaurants/{org.rst_south.pk}/").status_code == 404  # alias route
    assert c.get(f"{V1}/organizations/restaurants/{org.rst_south.pk}/").status_code == 404
    assert c.get(f"{V1}/organizations/restaurants/{org.rst_north.pk}/").status_code == 200
    codes = {r["code"] for r in c.get(f"{V1}/restaurants/", {"page_size": 50}).json()["results"]}
    assert codes == set(
        Restaurant.objects.filter(area__region=org.north).values_list("code", flat=True)
    )
    assert c.get(f"{V1}/organizations/companies/").json()["count"] == 0


def test_create_update_status_move_and_history(org, org_admin):
    c = api(org_admin)
    r = c.post(
        f"{V1}/organizations/restaurants/",
        {"parent_id": str(org.lhr_central.pk), "name": "API Store", "city_code": "LHR"},
        format="json",
    )
    assert r.status_code == 201, r.json()
    rid = r.json()["data"]["id"]
    assert r.json()["data"]["status"] == "planned" and r.json()["data"]["code"].startswith(
        "RST-LHR-"
    )
    r = c.patch(
        f"{V1}/organizations/restaurants/{rid}/",
        {"short_name": "API", "code": "HACK"},
        format="json",
    )
    assert (
        r.status_code == 200
        and r.json()["data"]["short_name"] == "API"
        and r.json()["data"]["code"] != "HACK"
    )
    r = c.post(
        f"{V1}/organizations/restaurants/{rid}/status/",
        {"action": "activate", "reason": "open"},
        format="json",
    )
    assert r.json()["data"]["status"] == "active"
    r = c.post(
        f"{V1}/organizations/restaurants/{rid}/status/",
        {"action": "activate", "reason": "again"},
        format="json",
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_status_transition"
    r = c.post(
        f"{V1}/organizations/restaurants/{rid}/move/",
        {"parent_id": str(org.lhr_north.pk), "reason": "rezoning"},
        format="json",
    )
    assert r.status_code == 200 and r.json()["data"]["parent"]["id"] == str(org.lhr_north.pk)
    events = [
        h["event"] for h in c.get(f"{V1}/organizations/restaurants/{rid}/history/").json()["data"]
    ]
    assert {"created", "updated", "activated", "moved"} <= set(events)


def test_invalid_hierarchy_and_validation_errors_use_envelope(org, org_admin):
    c = api(org_admin)
    r = c.post(
        f"{V1}/organizations/regions/",
        {"parent_id": str(org.corporate.pk), "name": "Wrong"},
        format="json",
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_hierarchy"
    r = c.post(
        f"{V1}/organizations/restaurants/",
        {"parent_id": str(org.lhr_central.pk), "name": "X", "city_code": "lahore"},
        format="json",
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error"
    r = c.post(
        f"{V1}/organizations/areas/",
        {"parent_id": str(org.north.pk), "name": "Lahore Central"},
        format="json",
    )
    assert r.status_code == 409


def test_scope_bypass_on_writes_is_blocked(org, scoped):
    south = scoped("region", org.south, email="south@example.com")
    c = api(south)
    # create under another region's area: parent lookup is scoped -> 404
    r = c.post(
        f"{V1}/organizations/restaurants/",
        {"parent_id": str(org.lhr_central.pk), "name": "X", "city_code": "LHR"},
        format="json",
    )
    assert r.status_code == 404
    # move own restaurant into another region: target not visible -> 404
    r = c.post(
        f"{V1}/organizations/restaurants/{org.rst_south.pk}/move/",
        {"parent_id": str(org.lhr_central.pk), "reason": "x"},
        format="json",
    )
    assert r.status_code == 404
    # close a restaurant in another region
    r = c.post(
        f"{V1}/organizations/restaurants/{org.rst_north.pk}/status/",
        {"action": "close", "reason": "x"},
        format="json",
    )
    assert r.status_code == 404
    org.rst_north.refresh_from_db()
    assert org.rst_north.status == "active"


def test_unmapped_methods_fail_closed(org, org_admin):
    c = api(org_admin)
    assert c.delete(f"{V1}/organizations/restaurants/{org.rst_north.pk}/").status_code in (403, 405)
    assert Restaurant.objects.filter(pk=org.rst_north.pk).exists()


def test_tree_endpoint(org, org_admin, scoped):
    tree = api(org_admin).get(f"{V1}/organizations/tree/").json()["data"]
    assert tree[0]["code"] == org.company.code
    ops = next(n for n in tree[0]["children"] if n["code"] == org.operations.code)
    assert ops["counts"]["restaurant"] == 10 and "url" not in ops
    south = scoped("region", org.south, perms=ORG_VIEW_PERMS, email="t@example.com")
    t2 = api(south).get(f"{V1}/organizations/tree/").json()["data"]
    assert t2[0]["context"] is True
    flat = str(t2)
    assert org.rst_south.code in flat and org.rst_north.code not in flat

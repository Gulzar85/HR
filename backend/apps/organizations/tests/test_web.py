"""Organization UI: rendering, permissions, scope/IDOR enforcement, forms, cascades, filters."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.organizations.hierarchy import ORG_TYPES
from apps.organizations.models import OrganizationHistory, Restaurant

from .conftest import ORG_VIEW_PERMS

pytestmark = pytest.mark.django_db


def test_all_pages_render_for_org_admin(client, org, org_admin):
    client.force_login(org_admin)
    urls = [
        reverse("organizations:dashboard"),
        reverse("organizations:tree"),
        reverse("organizations:tree") + "?inactive=1",
    ]
    samples = {
        "company": org.company, "division": org.operations, "corporate_location": org.lahore,
        "department": org.lhr_hr, "region": org.north, "area": org.lhr_central, "restaurant": org.rst_north,
    }  # fmt: skip
    for key, unit in samples.items():
        urls += [
            reverse(f"organizations:{key}_list"),
            reverse(f"organizations:{key}_create"),
            reverse(f"organizations:{key}_detail", args=[unit.pk]),
            reverse(f"organizations:{key}_edit", args=[unit.pk]),
            reverse(f"organizations:{key}_status", args=[unit.pk]),
        ]
        if ORG_TYPES[key].parent_key:
            urls.append(reverse(f"organizations:{key}_move", args=[unit.pk]))
    for url in urls:
        r = client.get(url)
        assert r.status_code == 200, url
        body = r.content.decode()
        assert "#DA291C" not in body.split("</style>", 1)[1], url  # theme tokens only


def test_tree_is_dynamic_and_complete(client, org, org_admin):
    client.force_login(org_admin)
    body = client.get(reverse("organizations:tree")).content.decode()
    for unit in (
        org.company,
        org.corporate,
        org.lahore,
        org.lhr_hr,
        org.north,
        org.lhr_central,
        org.rst_north,
    ):
        assert unit.code in body


def test_anonymous_and_unprivileged_access(client, org, make_user):
    url = reverse("organizations:restaurant_list")
    assert client.get(url).status_code == 302
    client.force_login(make_user("plain@example.com"))
    assert client.get(url).status_code == 403
    assert client.get(reverse("organizations:dashboard")).status_code == 403
    assert (
        client.get(reverse("organizations:restaurant_detail", args=[org.rst_north.pk])).status_code
        == 403
    )


def test_scoped_list_and_idor(client, org, scoped):
    user = scoped("region", org.south, perms=ORG_VIEW_PERMS, email="south@example.com")
    client.force_login(user)
    r = client.get(reverse("organizations:restaurant_list"))
    codes = {row["obj"].code for row in r.context["rows"]}
    assert codes == set(
        Restaurant.objects.filter(area__region=org.south).values_list("code", flat=True)
    )
    # direct UUID access to another region's restaurant: 404, indistinguishable from "missing"
    assert (
        client.get(reverse("organizations:restaurant_detail", args=[org.rst_north.pk])).status_code
        == 404
    )
    assert (
        client.get(reverse("organizations:region_detail", args=[org.north.pk])).status_code == 404
    )
    assert (
        client.get(reverse("organizations:restaurant_detail", args=[org.rst_south.pk])).status_code
        == 200
    )


def test_tree_for_scoped_user_shows_only_scope_plus_context(client, org, scoped):
    user = scoped("region", org.south, perms=ORG_VIEW_PERMS, email="tree@example.com")
    client.force_login(user)
    r = client.get(reverse("organizations:tree"))
    body = r.content.decode()
    assert org.south.code in body and org.rst_south.code in body
    assert org.rst_north.code not in body and org.lhr_hr.code not in body
    roots = r.context["tree"]
    assert roots[0]["context"] is True  # company shown for orientation only


def test_unauthorized_status_change_and_move_via_post(client, org, scoped):
    viewer = scoped("global", perms=ORG_VIEW_PERMS, email="viewer@example.com")
    client.force_login(viewer)
    r = client.post(
        reverse("organizations:restaurant_status", args=[org.rst_north.pk]),
        {"action": "close", "reason": "x"},
    )
    assert r.status_code == 403
    r = client.post(
        reverse("organizations:restaurant_move", args=[org.rst_north.pk]),
        {"area": org.lhr_north.pk, "reason": "x"},
    )
    assert r.status_code == 403
    org.rst_north.refresh_from_db()
    assert org.rst_north.status == "active" and org.rst_north.area == org.lhr_central


def test_out_of_scope_post_is_404(client, org, scoped):
    south_admin = scoped("region", org.south, email="sa@example.com")
    client.force_login(south_admin)
    r = client.post(
        reverse("organizations:restaurant_status", args=[org.rst_north.pk]),
        {"action": "close", "reason": "x"},
    )
    assert r.status_code == 404
    org.rst_north.refresh_from_db()
    assert org.rst_north.status == "active"


def test_close_restaurant_through_ui(client, org, org_admin):
    client.force_login(org_admin)
    url = reverse("organizations:restaurant_status", args=[org.rst_north.pk])
    assert client.post(url, {"action": "close"}).status_code == 200  # reason required -> form error
    r = client.post(url, {"action": "close", "reason": "Lease ended"})
    assert r.status_code == 302
    org.rst_north.refresh_from_db()
    assert org.rst_north.status == "closed"
    assert OrganizationHistory.objects.filter(
        entity_id=org.rst_north.pk, event="closed", reason="Lease ended"
    ).exists()
    # invalid action for the current status is not offered / not accepted
    r = client.post(url, {"action": "temporarily_close", "reason": "x"})
    assert r.status_code == 200 and "Select a valid choice" in r.content.decode()


def test_create_restaurant_with_cascade_validation(client, org, org_admin):
    client.force_login(org_admin)
    url = reverse("organizations:restaurant_create")
    form = client.get(url).content.decode()
    assert 'hx-get="/organizations/options/area/"' in form and 'hx-target="#id_area"' in form
    bad = client.post(
        url,
        {
            "region": org.south.pk,
            "area": org.lhr_central.pk,
            "name": "X",
            "city_code": "LHR",
            "status": "planned",
        },
    )
    assert (
        bad.status_code == 200 and "Select a valid choice" in bad.content.decode()
    )  # area not under that region
    ok = client.post(
        url,
        {
            "region": org.north.pk,
            "area": org.lhr_central.pk,
            "name": "Mall Road",
            "city_code": "LHR",
            "status": "planned",
        },
    )
    assert ok.status_code == 302
    created = Restaurant.objects.get(name="Mall Road")
    assert created.code.startswith("RST-LHR-") and ok.url == reverse(
        "organizations:restaurant_detail", args=[created.pk]
    )


def test_create_rejects_out_of_scope_parent(client, org, scoped):
    south_admin = scoped("region", org.south, email="sa2@example.com")
    client.force_login(south_admin)
    r = client.post(
        reverse("organizations:area_create"), {"region": org.north.pk, "name": "Sneaky"}
    )
    assert (
        r.status_code == 200 and "Select a valid choice" in r.content.decode()
    )  # not even offered


def test_options_endpoint_is_scoped(client, org, scoped):
    user = scoped("region", org.south, perms=ORG_VIEW_PERMS, email="opt@example.com")
    client.force_login(user)
    body = client.get(
        reverse("organizations:options", args=["area"]), {"region": org.north.pk}
    ).content.decode()
    assert org.lhr_central.code not in body  # other region's areas never leak
    body = client.get(
        reverse("organizations:options", args=["area"]), {"region": org.south.pk}
    ).content.decode()
    assert org.khi_south.code in body
    assert client.get(reverse("organizations:options", args=["nonsense"])).status_code == 404
    assert (
        client.get(reverse("organizations:options", args=["area"]), {"region": "bad"}).status_code
        == 404
    )


def test_search_filter_and_pagination(client, org, org_admin, settings):
    settings.EMS_ADMIN_PAGE_SIZE = 4
    client.force_login(org_admin)
    url = reverse("organizations:restaurant_list")
    r = client.get(url)
    assert len(r.context["rows"]) == 4 and r.context["page_obj"].paginator.count == 10
    r = client.get(url, {"q": org.rst_north.code})
    assert [row["obj"].pk for row in r.context["rows"]] == [org.rst_north.pk]
    r = client.get(url, {"region": org.south.pk})
    assert {row["obj"].area.region_id for row in r.context["rows"]} == {org.south.pk}
    r = client.get(url, {"area": org.lhr_north.pk, "status": "active"})
    assert r.context["page_obj"].paginator.count == org.lhr_north.restaurants.count()
    partial = client.get(url, {"q": "Lahore"}, HTTP_HX_REQUEST="true").content.decode()
    assert "<html" not in partial and "<table" in partial
    r = client.get(reverse("organizations:department_list"), {"corporate_location": org.karachi.pk})
    assert r.context["page_obj"].paginator.count == 5


def test_edit_cannot_change_code_or_parent(client, org, org_admin):
    client.force_login(org_admin)
    url = reverse("organizations:area_edit", args=[org.lhr_central.pk])
    client.post(
        url, {"name": "Central Lahore", "description": "", "code": "HACK-1", "region": org.south.pk}
    )
    org.lhr_central.refresh_from_db()
    assert org.lhr_central.name == "Central Lahore"
    assert org.lhr_central.code.startswith("AREA-") and org.lhr_central.region == org.north


def test_move_through_ui(client, org, org_admin):
    client.force_login(org_admin)
    r = client.post(
        reverse("organizations:restaurant_move", args=[org.rst_north.pk]),
        {"region": org.north.pk, "area": org.lhr_north.pk, "reason": "Re-zoning"},
    )
    assert r.status_code == 302
    org.rst_north.refresh_from_db()
    assert org.rst_north.area == org.lhr_north


def test_navigation_shows_organization_section_by_permission(client, org, org_admin, make_user):
    client.force_login(org_admin)
    assert "Structure tree" in client.get("/").content.decode()
    client.force_login(make_user("np@example.com"))
    assert "Structure tree" not in client.get("/").content.decode()


def test_cascade_clean_rejects_mismatch_even_if_queryset_not_narrowed(org, org_admin):
    """Defence in depth: CascadeMixin.clean() re-checks the child/parent relationship."""
    from apps.organizations.forms.units import RestaurantForm

    form = RestaurantForm(
        data={"area": org.lhr_central.pk, "name": "X", "city_code": "LHR", "status": "planned"},
        user=org_admin,
    )
    form.data = form.data.copy()
    form.data["region"] = str(org.south.pk)  # set after init: queryset was not narrowed
    assert not form.is_valid()
    assert "within the selected region" in str(form.errors)

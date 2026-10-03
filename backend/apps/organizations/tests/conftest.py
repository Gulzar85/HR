from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.accounts.models import UserScope
from apps.accounts.seed import ORG_ADMIN_PERMS, ORG_VIEW_PERMS
from apps.organizations.models import (
    Area,
    Company,
    CorporateLocation,
    Department,
    Division,
    Region,
    Restaurant,
    StructureType,
)
from apps.organizations.seed import seed_organization


@pytest.fixture
def org(db):
    """Seeded hierarchy: CMP-001 > Corporate (Lahore, Karachi x 5 depts) + Operations > 2 regions >
    2 areas each > 2-3 active restaurants each."""
    seed_organization(sample_operations=True)
    company = Company.objects.get()
    return SimpleNamespace(
        company=company,
        corporate=Division.objects.get(structure_type=StructureType.CORPORATE),
        operations=Division.objects.get(structure_type=StructureType.OPERATIONS),
        lahore=CorporateLocation.objects.get(city_code="LHR"),
        karachi=CorporateLocation.objects.get(city_code="KHI"),
        lhr_hr=Department.objects.get(code="DEPT-LHR-HR"),
        north=Region.objects.get(name="North Region"),
        south=Region.objects.get(name="South Region"),
        lhr_central=Area.objects.get(name="Lahore Central"),
        lhr_north=Area.objects.get(name="Lahore North"),
        khi_south=Area.objects.get(name="Karachi South"),
        rst_north=Restaurant.objects.filter(area__region__name="North Region")
        .order_by("code")
        .first(),
        rst_south=Restaurant.objects.filter(area__region__name="South Region")
        .order_by("code")
        .first(),
    )


def grant(user, scope_type: str, unit=None, *, descendants: bool = True):
    ref = "*" if unit is None else str(unit.pk)
    return UserScope.objects.create(
        user=user, scope_type=scope_type, scope_ref=ref, include_descendants=descendants
    )


@pytest.fixture
def org_admin(make_user):
    """Organization administrator with organization-wide (global) scope."""
    user = make_user("orgadmin@example.com", perms=ORG_ADMIN_PERMS)
    grant(user, "global")
    return user


@pytest.fixture
def scoped(make_user):
    """Factory: user with the given permissions and one scope on a unit."""

    def _make(scope_type: str, unit=None, perms=None, descendants: bool = True, email=None):
        user = make_user(email, perms=perms if perms is not None else ORG_ADMIN_PERMS)
        grant(user, scope_type, unit, descendants=descendants)
        return user

    return _make


__all__ = ["ORG_VIEW_PERMS", "grant"]

"""Mounted by apps/api/v1/urls.py at /api/v1/organizations/ (and short aliases for operations units)."""

from django.urls import path

from ..hierarchy import ORG_TYPES
from . import views as v


def unit_patterns(key: str) -> list:
    return [
        path("", v.build(v.OrgListCreateAPI, key).as_view(), name=f"{key}-list"),
        path("<uuid:pk>/", v.build(v.OrgDetailAPI, key).as_view(), name=f"{key}-detail"),
        path("<uuid:pk>/status/", v.build(v.OrgStatusAPI, key).as_view(), name=f"{key}-status"),
        path("<uuid:pk>/history/", v.build(v.OrgHistoryAPI, key).as_view(), name=f"{key}-history"),
        *(
            [path("<uuid:pk>/move/", v.build(v.OrgMoveAPI, key).as_view(), name=f"{key}-move")]
            if ORG_TYPES[key].parent_key
            else []
        ),
    ]


organization_urlpatterns = [
    path("tree/", v.OrganizationTreeAPI.as_view(), name="organization-tree")
]
for _key, _t in ORG_TYPES.items():
    organization_urlpatterns.append(path(f"{_t.slug}/", (unit_patterns(_key), None, None)))

# Short aliases used by the Electron client examples: /api/v1/regions/, /areas/, /restaurants/
alias_urlpatterns = {key: unit_patterns(key) for key in ("region", "area", "restaurant")}

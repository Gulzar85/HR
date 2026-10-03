"""Organization web URLs: /organizations/<type-slug>/[<uuid>/[edit|status|move]/]."""

from django.urls import path

from .hierarchy import ORG_TYPES
from .views.areas import views as areas
from .views.companies import views as companies
from .views.departments import views as departments
from .views.divisions import views as divisions
from .views.hierarchy import views as hierarchy
from .views.locations import views as locations
from .views.regions import views as regions
from .views.restaurants import views as restaurants

app_name = "organizations"

MODULES = {
    "company": (companies, "Company"),
    "division": (divisions, "Division"),
    "corporate_location": (locations, "CorporateLocation"),
    "department": (departments, "Department"),
    "region": (regions, "Region"),
    "area": (areas, "Area"),
    "restaurant": (restaurants, "Restaurant"),
}

urlpatterns = [
    path("", hierarchy.OrganizationDashboardView.as_view(), name="dashboard"),
    path("tree/", hierarchy.OrganizationTreeView.as_view(), name="tree"),
    path("options/<str:type_key>/", hierarchy.OrganizationOptionsView.as_view(), name="options"),
]

for key, (module, cls) in MODULES.items():
    slug = ORG_TYPES[key].slug
    urlpatterns += [
        path(f"{slug}/", getattr(module, f"{cls}ListView").as_view(), name=f"{key}_list"),
        path(f"{slug}/new/", getattr(module, f"{cls}CreateView").as_view(), name=f"{key}_create"),
        path(
            f"{slug}/<uuid:pk>/",
            getattr(module, f"{cls}DetailView").as_view(),
            name=f"{key}_detail",
        ),
        path(
            f"{slug}/<uuid:pk>/edit/",
            getattr(module, f"{cls}UpdateView").as_view(),
            name=f"{key}_edit",
        ),
        path(
            f"{slug}/<uuid:pk>/status/",
            getattr(module, f"{cls}StatusView").as_view(),
            name=f"{key}_status",
        ),
    ]
    if hasattr(module, f"{cls}MoveView"):
        urlpatterns.append(
            path(
                f"{slug}/<uuid:pk>/move/",
                getattr(module, f"{cls}MoveView").as_view(),
                name=f"{key}_move",
            )
        )

from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    name = "apps.organizations"
    label = "organizations"
    verbose_name = "Organizations"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.common.navigation import register_nav_item, register_nav_section

        from . import data_quality  # noqa: F401  (registers checks)
        from .services import register_organization_scopes

        register_organization_scopes()  # Phase 1 UserScope now resolves real organization units

        register_nav_section("organization", "Organization", order=20)
        items = [
            ("Overview", "organizations:dashboard", "layout-grid", "organizations.view_organization_structure", "org_dashboard"),
            ("Structure tree", "organizations:tree", "network", "organizations.view_organization_structure", "org_tree"),
            ("Companies", "organizations:company_list", "building-2", "organizations.view_company", "company"),
            ("Divisions", "organizations:division_list", "git-fork", "organizations.view_division", "division"),
            ("Corporate locations", "organizations:corporate_location_list", "landmark", "organizations.view_corporatelocation", "corporate_location"),
            ("Departments", "organizations:department_list", "briefcase", "organizations.view_department", "department"),
            ("Regions", "organizations:region_list", "map", "organizations.view_region", "region"),
            ("Areas", "organizations:area_list", "map-pinned", "organizations.view_area", "area"),
            ("Restaurants", "organizations:restaurant_list", "store", "organizations.view_restaurant", "restaurant"),
        ]  # fmt: skip
        for order, (label, url, icon, perm, key) in enumerate(items):
            register_nav_item(
                "organization", label, url, icon=icon, permission=perm, key=key, order=order
            )

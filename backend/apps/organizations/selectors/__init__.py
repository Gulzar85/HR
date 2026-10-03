"""Organization selectors (read-only, scope-aware when a user is passed)."""

from .area_selectors import get_areas, get_areas_by_region
from .company_selectors import get_active_companies, get_active_divisions
from .department_selectors import (
    get_corporate_locations,
    get_departments,
    get_departments_by_location,
)
from .organization_selectors import (
    ancestor_of_type_on,
    ancestors_on,
    children_of,
    counts_for,
    get_organization_tree,
    get_unit_for_user,
    history_for,
    parent_on,
    relationships_for,
    visible_units,
)
from .region_selectors import get_regions
from .restaurant_selectors import (
    get_restaurants,
    get_restaurants_by_area,
    get_restaurants_by_region,
)

__all__ = [
    "ancestor_of_type_on",
    "ancestors_on",
    "children_of",
    "counts_for",
    "get_active_companies",
    "get_active_divisions",
    "get_areas",
    "get_areas_by_region",
    "get_corporate_locations",
    "get_departments",
    "get_departments_by_location",
    "get_organization_tree",
    "get_regions",
    "get_restaurants",
    "get_restaurants_by_area",
    "get_restaurants_by_region",
    "get_unit_for_user",
    "history_for",
    "parent_on",
    "relationships_for",
    "visible_units",
]

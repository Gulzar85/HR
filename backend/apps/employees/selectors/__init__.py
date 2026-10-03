"""Employee-domain read queries (scope-aware, N+1-free)."""

from .contact_selectors import find_contacts, shared_contact_values
from .employee_selectors import (
    get_employee,
    get_employee_addresses,
    get_employee_by_code,
    get_employee_by_user,
    get_employee_contacts,
    get_employee_detail,
    get_employee_emergency_contacts,
    get_employee_identifiers,
    get_employee_list,
    get_employee_timeline,
    search_employees,
)
from .person_selectors import get_person, get_person_relationships

__all__ = [
    "find_contacts",
    "get_employee",
    "get_employee_addresses",
    "get_employee_by_code",
    "get_employee_by_user",
    "get_employee_contacts",
    "get_employee_detail",
    "get_employee_emergency_contacts",
    "get_employee_identifiers",
    "get_employee_list",
    "get_employee_timeline",
    "get_person",
    "get_person_relationships",
    "search_employees",
    "shared_contact_values",
]

"""Employee-domain permission names (convention: ``<app_label>.<action>_<noun>``).

Declared in ``Employee.Meta.permissions`` so ``migrate`` creates them, checked through
``apps.accounts.services.PermissionService`` and granted to roles by
``apps.accounts.seed`` / the admin permission matrix. Nothing in this app uses a permission that is
not listed here.

Three tiers, mirrored by docs/security/employee-data.md:

* **Baseline** - ``view_employee`` plus the CRUD verbs. Needed to work with an employee at all.
* **Sensitive read** - ``view_sensitive_identity``, ``view_identifiers``,
  ``view_sensitive_contacts``, ``view_emergency_contacts``. Read access to personal data; withheld
  from ordinary HR users on purpose.
* **Privileged write** - ``link_user``, ``archive_employee``, ``export_employee`` and the ``manage_*``
  families. Each one changes or reveals something an ordinary HR user must not be able to.
"""

VIEW = "employees.view_employee"
ADD = "employees.add_employee"
CHANGE = "employees.change_employee"

VIEW_PERSON = "employees.view_person"
ADD_PERSON = "employees.add_person"
CHANGE_PERSON = "employees.change_person"

# --- sensitive reads (ADR-021) -------------------------------------------------
VIEW_SENSITIVE_IDENTITY = "employees.view_sensitive_identity"
VIEW_IDENTIFIERS = "employees.view_identifiers"
VIEW_SENSITIVE_CONTACTS = "employees.view_sensitive_contacts"
VIEW_EMERGENCY_CONTACTS = "employees.view_emergency_contacts"

# --- privileged writes ---------------------------------------------------------
ARCHIVE = "employees.archive_employee"
LINK_USER = "employees.link_user"
EXPORT = "employees.export_employee"
VIEW_TIMELINE = "employees.view_employee_timeline"

MANAGE_CONTACTS = "employees.manage_contacts"
MANAGE_ADDRESSES = "employees.manage_addresses"
MANAGE_EMERGENCY_CONTACTS = "employees.manage_emergency_contacts"
MANAGE_IDENTIFIERS = "employees.manage_identifiers"
MANAGE_RELATIONSHIPS = "employees.manage_relationships"
MANAGE_NOTES = "employees.manage_notes"

#: Permission sets used by views, the DRF layer and the seed roles.
SENSITIVE_READ_PERMS = (
    VIEW_SENSITIVE_IDENTITY,
    VIEW_IDENTIFIERS,
    VIEW_SENSITIVE_CONTACTS,
    VIEW_EMERGENCY_CONTACTS,
)

BASIC = (VIEW, ADD, CHANGE)

BASIC_WITH_PERSON = (*BASIC, VIEW_PERSON, ADD_PERSON, CHANGE_PERSON)

HR_OFFICER_PERMS = (
    *BASIC_WITH_PERSON,
    MANAGE_CONTACTS,
    MANAGE_ADDRESSES,
    MANAGE_EMERGENCY_CONTACTS,
    MANAGE_NOTES,
    VIEW_TIMELINE,
)

HR_MANAGER_PERMS = (
    *HR_OFFICER_PERMS,
    VIEW_SENSITIVE_CONTACTS,
    VIEW_EMERGENCY_CONTACTS,
    VIEW_SENSITIVE_IDENTITY,
    VIEW_IDENTIFIERS,
    MANAGE_IDENTIFIERS,
    MANAGE_RELATIONSHIPS,
    ARCHIVE,
)

HR_ADMIN_PERMS = (*HR_MANAGER_PERMS, LINK_USER, EXPORT)


def can_view_sensitive_identity(user) -> bool:
    """Single place that decides whether unmasked identity data may be rendered."""
    from apps.accounts.services import PermissionService

    return PermissionService.can(user, VIEW_SENSITIVE_IDENTITY)


def can_view_identifiers(user) -> bool:
    from apps.accounts.services import PermissionService

    return PermissionService.can(user, VIEW_IDENTIFIERS)

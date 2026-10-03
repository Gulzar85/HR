"""Default (editable) roles. Roles are data: administrators can add/change them in the UI.

Only the permission sets that exist today are seeded; later phases extend them via their own
seed step (``seed_identity`` is idempotent and never removes permissions an admin added).
"""

from __future__ import annotations

from django.contrib.auth.models import Permission

from .models import Role

ACCOUNT_ADMIN_PERMS = [
    "accounts.view_user", "accounts.add_user", "accounts.change_user",
    "accounts.view_role", "accounts.manage_users", "accounts.manage_roles",
    "accounts.manage_permissions", "accounts.view_security_history", "audit.view_audit_logs",
]  # fmt: skip

ORG_MODELS = [
    "company",
    "division",
    "corporatelocation",
    "department",
    "region",
    "area",
    "restaurant",
]
ORG_VIEW_PERMS = [f"organizations.view_{m}" for m in ORG_MODELS] + [
    "organizations.view_organization_structure",
    "organizations.view_organization_history",
]
ORG_ADMIN_PERMS = (
    ORG_VIEW_PERMS
    + [f"organizations.{action}_{m}" for m in ORG_MODELS for action in ("add", "change")]
    + ["organizations.change_organization_status", "organizations.move_organization"]
)
OPS_MANAGER_PERMS = [
    "organizations.view_region", "organizations.view_area", "organizations.view_restaurant",
    "organizations.view_organization_structure",
]  # fmt: skip

# Employee domain (Phase 3) - permission sets defined once in apps.employees.permissions.
from apps.employees.permissions import (  # noqa: E402
    HR_ADMIN_PERMS,
    HR_MANAGER_PERMS,
    HR_OFFICER_PERMS,
)

DEFAULT_ROLES: list[tuple[str, str, str, list[str]]] = [
    ("System Administrator", "system-administrator", "Full identity, access and organization administration.", ACCOUNT_ADMIN_PERMS + ORG_ADMIN_PERMS + list(HR_ADMIN_PERMS)),
    ("HR Administrator", "hr-administrator", "HR administration across the organization.", ORG_VIEW_PERMS + list(HR_ADMIN_PERMS)),
    ("HR Manager", "hr-manager", "Manages the HR function.", list(HR_MANAGER_PERMS)),
    ("Corporate Manager", "corporate-manager", "Corporate location management.", []),
    ("Regional Manager", "regional-manager", "Manages a region.", OPS_MANAGER_PERMS),
    ("Area Manager", "area-manager", "Manages an area.", OPS_MANAGER_PERMS),
    ("Restaurant Manager", "restaurant-manager", "Manages a restaurant.", OPS_MANAGER_PERMS),
    ("Department Manager", "department-manager", "Manages a department.", []),
    ("HR Officer", "hr-officer", "Day-to-day HR operations.", list(HR_OFFICER_PERMS)),
    ("Recruiter", "recruiter", "Recruitment / ATS operations.", []),
    ("Auditor", "auditor", "Read-only access to audit and security history.",
     ["accounts.view_user", "accounts.view_security_history", "audit.view_audit_logs"]),
    ("Report Viewer", "report-viewer", "Views reports.", []),
    ("Employee", "employee", "Baseline self-service access.", []),
]  # fmt: skip


def seed_roles() -> dict[str, int]:
    created = missing = 0
    for name, code, description, perms in DEFAULT_ROLES:
        role, was_created = Role.objects.get_or_create(
            code=code, defaults={"name": name, "description": description, "is_system": True}
        )
        created += was_created
        for label in perms:
            app, codename = label.split(".")
            perm = Permission.objects.filter(content_type__app_label=app, codename=codename).first()
            if perm is None:
                missing += 1
                continue
            role.permissions.add(perm)
    return {"created": created, "missing_permissions": missing}

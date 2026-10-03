"""Permission names used by the identity UI/API. Convention: ``<app_label>.<action>_<noun>``.

Future apps define their own in ``permissions/`` the same way (employees.view_employee,
recruitment.manage_offer, ...) and check them through ``PermissionService`` / ``HasPerm``.
"""

VIEW_USER = "accounts.view_user"
ADD_USER = "accounts.add_user"
CHANGE_USER = "accounts.change_user"
MANAGE_USERS = "accounts.manage_users"
VIEW_ROLE = "accounts.view_role"
MANAGE_ROLES = "accounts.manage_roles"
MANAGE_PERMISSIONS = "accounts.manage_permissions"
VIEW_SECURITY_HISTORY = "accounts.view_security_history"
VIEW_AUDIT_LOGS = "audit.view_audit_logs"

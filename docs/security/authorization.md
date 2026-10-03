# Authorization

**Backend authorization is authoritative.** Hiding a button is a UX hint, never a control (ADR-012).

## Layers of a decision
1. **Authenticated & active** - inactive/suspended/locked users never pass.
2. **Permission** - `PermissionService.can(user, "app.codename")` (direct + groups + roles).
3. **Scope** - `ScopeService` narrows *which rows* (fail closed).
4. **Object permission** - django-guardian grant on a specific object (`PermissionService.can_access_object`).
5. **Service rules** - self-change prohibition, escalation guard, superuser protection.

## Web
Views use `AdminAccessMixin` (login + `permission_required`; anonymous → login redirect, authenticated without permission → 403). The services check again, so a forged POST cannot bypass the view. Action views are POST-only.

| Capability | Permission |
|---|---|
| List/view users, roles, groups | `accounts.view_user`, `accounts.view_role` |
| Create / edit user | `accounts.add_user`, `accounts.change_user` |
| Lifecycle, password set/reset link, roles/groups/scopes of a user, session revoke | `accounts.manage_users` |
| Create/edit roles & groups, membership | `accounts.manage_roles` |
| Change permissions carried by roles/groups, direct user permissions | `accounts.manage_permissions` |
| Security history | `accounts.view_security_history` |
| Audit log | `audit.view_audit_logs` |

## API
`HasPerm` + `permission_map`; unmapped methods are denied. Errors use the standard envelope (`401 authentication_failed|token_not_valid`, `403 permission_denied`, `409 conflict`, `422 business_rule_violation`).

## Superusers
Bypass permission checks (Django). Their actions still produce audit rows; they cannot be impersonated or managed by non-superusers; there is no silent impersonation.

## Writing authorization for a new module
```python
class EmployeeListView(AdminAccessMixin, ListView):
    permission_required = "employees.view_employee"
    def get_queryset(self):
        return ScopeService.filter_queryset_by_scope(self.request.user, EmployeeSelector.all(), EMPLOYEE_SCOPE_LOOKUPS)
```
Do not write `if user.is_manager`. Roles are data; permissions are the contract.

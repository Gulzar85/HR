# Identity & Access Architecture (Phase 1)

```
Authentication → User → Roles / Groups → Permissions → Access Scope → Object permission → Service → Domain
```

## Concepts (and why each exists)

| Concept | What it is | Where | Why it exists |
|---|---|---|---|
| **User** | A login identity. Email is the login identifier. | `accounts.User` | *Who is signing in.* No employee data. |
| **Status** | `pending / active / suspended / locked / inactive` | `User.status` (source of truth; `is_active` is derived) | Lifecycle & security states with different meanings. |
| **Permission** | A business capability `app.action_noun` | Django `auth.Permission` | The only permission system. No custom engine. |
| **Role** | Administrator-managed *set of permissions* for a job function | `accounts.Role` (+`UserRole`) | *What a person may do.* Data, not code. |
| **Group** | A *collection of users* (team, panel) that may carry permissions | Django `Group` + `GroupProfile` (UUID, description, active flag) | *Who belongs together.* Reuses Django groups. |
| **Scope** | *Where* permissions apply: `(scope_type, scope_ref)` | `accounts.UserScope` | Organization-aware access without coupling to org models. |
| **Object permission** | Per-object grant | django-guardian | Exceptions on a single record. |

Effective permissions = direct + active groups + active roles (`accounts.backends.IdentityBackend`). Superusers pass permission checks (Django semantics) but all privileged changes stay audited. `is_staff` only allows the Django-admin fallback UI. **They are not interchangeable**: `is_staff` ≠ `is_superuser` ≠ role ≠ permission ≠ scope.

## User ≠ Employee
`User` has no employee/org columns. Phase 3 adds a nullable link from the *employee* side. A user can exist without an employee (administrators) and an employee without a user (crew without login). See ADR-008.

## Layers
```
Views / API views (HTTP, authn, form handling)
   → services:  UserService · RoleService · PermissionService · ScopeService · SessionService · AuthenticationService
   → selectors: UserSelector · RoleSelector · GroupSelector · permission_selectors
   → models + audit (AccountEvent, LoginEvent, AuditLog) + outbox events
```
Views never touch the ORM for writes and never decide authorization with ad-hoc conditions. Every service re-checks permissions (defence in depth) and is atomic (`@transactional`).

## Public contract for later phases
```python
from apps.accounts.services import PermissionService, ScopeService, register_scope_type

PermissionService.can(user, "employees.change_employee")            # capability
PermissionService.can_access_object(user, "employees.view_employee", employee)  # + guardian object grant
PermissionService.objects_for_user(user, "employees.view_employee", Employee.objects.all())
ScopeService.get_user_scopes(user)
ScopeService.can_access_scope(user, "restaurant", "RST-LHR-001")
ScopeService.filter_queryset_by_scope(user, qs, {"region": "restaurant__area__region_id", "restaurant": "restaurant_id"})
```
API views declare `permission_classes = [HasPerm]` and `permission_map = {"GET": "app.view_x", ...}` (unmapped methods are denied).

## Scopes and Phase 2
`scope_type` strings are registered in `scope_service.register_scope_type` (company, corporate_location, department, region, area, restaurant, global are pre-registered as *names only*). In Phase 2 the Organization app re-registers each type with
* `descendants(ref) -> [(type, ref)...]` so a Region scope covers its Areas/Restaurants, and
* `validator(ref) -> bool` so grants must reference existing units.
No migration or API change is needed in accounts. Querysets are narrowed with `filter_queryset_by_scope` using a lookup map supplied by the *domain* app. No scope ⇒ no data (fail closed). A user cannot grant a scope they do not hold or change their own scopes.

## Guards enforced in services
* No self-service changes to roles/groups/permissions/scopes/status.
* **Privilege-escalation guard**: you cannot grant *or strip* permissions you do not hold.
* Only superusers manage superuser accounts.
* Owner-bound lookups (sessions, scopes) prevent IDOR.

## Naming convention for permissions
`<app_label>.<action>_<noun>`: `view|add|change|delete` (Django defaults) plus verbs for business capabilities: `manage_*`, `approve_*`, `export_*`, `download_*`, `hire_*`. Examples: `employees.view_employee`, `recruitment.manage_offer`, `recruitment.hire_candidate`, `accounts.manage_users`, `audit.view_audit_logs`. Only meaningful capabilities become permissions, never one per button. Internal/append-only models are excluded from the role editor (`PermissionService.assignable_permissions`).

## Seeding
`python manage.py seed_identity` creates the example roles (idempotent, editable afterwards).

## Impersonation
Not implemented. A future implementation must require an explicit permission, record admin + target + start/end in the audit log, never reveal the target's password, and never hide the administrator's identity.

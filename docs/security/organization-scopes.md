# Organization scopes

A `UserScope` is `(scope_type, scope_ref)`. Phase 2 makes the types real:

| scope_type | ref | covers (with `include_descendants`) |
|---|---|---|
| `global` | `*` | everything |
| `company` | company UUID | all units of that company |
| `division` | division UUID | its locations and departments, or its regions, areas and restaurants |
| `corporate_location` | UUID | the location and its departments |
| `department` | UUID | the department |
| `region` | UUID | the region, its areas and restaurants |
| `area` | UUID | the area and its restaurants |
| `restaurant` | UUID | the restaurant |

* With `include_descendants=False` the scope covers only the unit itself.
* No scope means no organization data (fail closed). A scope never grants the *parent* of its unit.
* Administrators may type a business code (for example `RST-LHR-001`). It is normalised to the UUID, which stays stable.

## How it is wired (ADR-016)
`accounts` never imports `organizations`. At start-up `OrganizationsConfig.ready()` calls `register_organization_scopes()`, which registers each type with `ScopeService` callbacks: `ancestors`, `descendants`, `validator`, `normalizer` and `describe`.

Phase 1 API (unchanged) plus additions:

* `ScopeService.user_can_access_organization(user, type, ref)`, an alias of `can_access_scope`. It uses the target's ancestors (one indexed query).
* `ScopeService.get_ancestors(type, ref)`, `get_descendants(type, ref)` and `resolve_user_organization_scopes(user)` (rows with labels).
* `ScopeService.filter_queryset_by_scope(user, qs, lookups, own_type=None)`. Hierarchical lookups resolve inheritance with SQL joins, so nothing is expanded in memory.
* A user's scopes are memoised on the user instance for one request and cleared on grant or revoke.

## For domain code
```python
from apps.organizations.services import OrganizationScopeService
from apps.organizations.hierarchy import scope_lookups

OrganizationScopeService.visible(user, "restaurant")                      # restaurants in scope
OrganizationScopeService.filter_queryset(user, Assignment.objects.all(), "restaurant", prefix="restaurant")
scope_lookups("restaurant", "restaurant")  # {"restaurant": "restaurant_id", "area": "restaurant__area_id", ...}
```

## Enforcement rules
* Detail, edit, status and move views and every API endpoint look objects up through the scoped queryset. An out-of-scope UUID returns **404**, the same as a missing one, so knowing a UUID grants nothing.
* Writes need the model permission (for example `organizations.change_restaurant`, `organizations.change_organization_status`, `organizations.move_organization`) **and** scope:
  * creating a unit needs scope on its parent;
  * a move needs scope on both the unit and the new parent;
  * a company needs global scope.
* Granting a scope requires the granter to hold that scope (Phase 1 rule), now resolved through the real hierarchy.
* Select options, filters and the options endpoint only list units in scope. The server re-validates every submitted choice.
* The tree shows a scoped user's units plus their ancestors, which are greyed out and not links (`context=True`).

## Permissions
`organizations.view_|add_|change_<model>`, `organizations.change_organization_status`, `organizations.move_organization`, `organizations.view_organization_history`, `organizations.view_organization_structure` (overview and tree). There is no delete permission in use. `seed_identity` grants:
* System Administrator: everything.
* HR Administrator: view.
* Regional, Area and Restaurant Manager: view regions, areas, restaurants and the tree.

Scopes decide *where* those permissions apply.

# Organization Management (Phase 2)

The organizational master-data foundation used by scopes, employees, assignments, recruitment and reports.

## Locked hierarchy

```
Company
├── Division [structure_type=CORPORATE]   e.g. "Corporate"
│   └── CorporateLocation                 e.g. Lahore (LHR), Karachi (KHI)
│       └── Department                    Finance, HR, IT, Supply Chain, Corporate Operations (per location)
└── Division [structure_type=OPERATIONS]  e.g. "Operations"
    └── Region
        └── Area
            └── Restaurant
```

* One explicit model per level, each with a single typed parent FK (`PROTECT`). No "giant organization model".
* Division *names* are data. The `structure_type` (CORPORATE / OPERATIONS) decides which children are valid.
* The structure is declared once in `apps/organizations/hierarchy.py` (`ORG_TYPES`). Services, selectors, scopes, the tree, forms and the API all derive parents, children and ORM paths from it (ADR-013, ADR-017).
* Several companies are supported in the data model (codes `CMP-001`, `CMP-002`, ...). This is not SaaS multi-tenancy, and moving units between companies is not allowed.

## Common unit fields
UUID primary key, immutable `code`, `name`, `description`, `status`, `effective_from`, `effective_to` (last effective day, inclusive), timestamps.

| Type | Code format | Extra fields |
|---|---|---|
| Company | `CMP-001` | legal name, registration and tax numbers, address, contacts, `theme_key` (reference only; branding stays in `apps/theme`) |
| Division | `DIV-CORP-001`, `DIV-OPS-001` | `structure_type` |
| CorporateLocation | `LOC-LHR-001` | city, `city_code` (3 letters), address, contacts |
| Department | `DEPT-LHR-HR` | `short_code` (unique per location) |
| Region | `REG-001` | none |
| Area | `AREA-001` | none |
| Restaurant | `RST-LHR-001` | short name, city, `city_code`, address, lat/long, contacts, opening/closing dates |

Codes come from `apps.common.services.generate_code` (row-locked sequences), except departments, which use the deterministic `DEPT-<city>-<short>`. Codes never change, even after a move (ADR-014).

## Status

| Types | Statuses | Transitions |
|---|---|---|
| Company … Area | planned, active, inactive, archived | activate (planned/inactive→active), deactivate (planned/active→inactive), archive (inactive→archived) |
| Restaurant | planned, active, temporarily_closed, closed, archived | activate (planned→active, sets opening date), temporarily_close, reopen (temp/closed→active, clears closing date), close (sets closing date), archive (closed/planned) |

Integrity rules, enforced in `OrgUnitService`:
* A unit can only become active while its parent is active.
* A unit cannot leave the live set (planned, active, temporarily closed) while it still has live children.
* New units cannot be added under a unit that isn't live.
* An active unit cannot be created or moved under a parent that isn't active.
* `effective_to` is set when a unit stops being live and cleared on reactivation.

Units are never deleted. The Django admin is read-only, and the API has no DELETE.

## History
* `OrganizationRelationship` stores effective-dated parent links as half-open intervals `[from, to)`. A move on date D closes the old row at D and opens a new one from D. A partial unique index allows only one current parent per unit.
* `OrganizationHistory` records created, updated, renamed, activated, deactivated, archived, moved, temporarily_closed, closed and reopened: who, when, before/after, reason and effective date. Every entry is mirrored to `AuditLog` (ADR-015).
* As-of-date queries: `parent_on()`, `ancestors_on()` and `ancestor_of_type_on(restaurant, "region", date(2025, 6, 30))`.

## Layers
```
Web views / API views ──► OrganizationService ──► per-type services (CompanyService … RestaurantService)
                                          └─► OrgUnitService (permission + scope + hierarchy + status + history, atomic)
Selectors: visible_units, children_of, get_organization_tree, counts_for, as-of-date helpers, per-type functions
```
Web and API call the same services. Neither talks to the ORM for writes.

## UI
`/organizations/` has the overview counts. `/organizations/tree/` has the dynamic tree, using native `<details>` with no SPA. Each type has list (search, filters, pagination, HTMX partials), detail (ancestry, children, history, parent history), create, edit, status (with reason and effective date) and move pages. Cascading selects use `forms/cascade.py` (`CascadeMixin`) and `organizations:options`.

## Data quality
Checks are registered in `apps.data_quality.registry`:
* unit without a current relationship
* relationship different from the FK
* live unit under a parent that isn't live
* wrong division structure, or a child starting before its parent
* duplicate codes (case-insensitive)
* dates that don't match the status
* overlapping relationships

Run them with `python manage.py validate_organization`. Database constraints already make an orphan restaurant, area or department impossible (NOT NULL + PROTECT).

## Commands
* `seed_organization [--sample-operations] [--force]`: idempotent. Refuses to run when DEBUG is off unless `--force`.
* `validate_organization`: read-only; exits 1 on errors.
* `organization_tree [--active-only]`: read-only.

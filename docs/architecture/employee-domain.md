# Employee domain (Phase 3)

`apps.employees` owns the **person and employee master record**. It stops at identity. Employment, positions, assignments, managers and pay belong to later phases (`employment`, `positions`, `assignments`), which will reference `Employee` and are never modelled on it (ADR-019).

## Aggregates
| Model | Purpose |
|---|---|
| `Person` | A human being: names, date of birth, gender, nationality and photo. It can exist without an employee record (ADR-018). |
| `Employee` | One per person. Holds an immutable code (`EMP-000001` from `common.codes.generate_code`), a status (`active`/`inactive`/`archived`) and an optional `User` link (ADR-008). |
| `EmployeeIdentifier` | CNIC, passport and similar. Sensitive: stored normalized, unique per type and number, masked by default, with a verification state (ADR-020). |
| `Contact` | Email, mobile and phone. At most one primary per type. |
| `Address` | Effective-dated history. Superseded rows are closed, never deleted. |
| `EmergencyContact`, `PersonRelationship` | Next of kin and links between people. |
| `EmployeeNote` | Internal or restricted notes. |
| `TimelineEntry` | A human-readable history per employee; entries can be marked sensitive. |

## Layers
- **Services** (`services/`): the only write path. Each one checks permission and scope (`authorize`), validates, writes, records an audit row, adds a timeline entry and enqueues an outbox event, all in one transaction.
- **Selectors** (`selectors/`): every read goes through the scoped `visible_employees` queryset. They use `select_related` and `Prefetch` so the list runs a constant number of queries.
- **Views**: class-based only. List (django-filter and HTMX), detail with HTMX inline section editors, create, edit, status, account link, authorised photo serving, identifier reveal and CSV export.
- **API**: `/api/v1/employees/`, with separate serializers per purpose (see `docs/api/employees.md`).
- **Events**: `EmployeeCreated`, `EmployeeUpdated`, `EmployeeStatusChanged`, `EmployeeArchived`, `EmployeeReactivated`, `EmployeeUserLinked` and `EmployeeUserUnlinked`, plus identifier, contact and address changes. All are published through the outbox.
- **Data quality**: `EMP-*` checks registered with `apps.data_quality`. They cover duplicate identifiers, emails and phones, possible duplicate people, invalid dates of birth, multiple primaries, missing or invalid contacts, invalid addresses and missing codes. Findings never echo sensitive values.

## Scope
`scope.py` grants access only to users with a global scope and to superusers; everyone else sees nothing (fails closed, ADR-022). Phase 4 plugs in an organization-based resolver through `register_employee_scope_resolver`. Out-of-scope records return 404.

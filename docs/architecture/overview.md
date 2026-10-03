# Architecture Overview

McDonald's Pakistan EMS is a **modular monolith** (Django 6.1) organised by domain. One deployable, many bounded apps under `backend/apps/`.

```
Web UI (CBVs + HTMX + Alpine)        Electron / Mobile / External
            │                                   │
            │                              REST API (/api/v1/)
            └──────────────┬────────────────────┘
                     Application layer
                           │
                        Services        (writes, transactions, workflows)
                           │
                     Domain logic
                           │
                  Selectors (reads)
                           │
                       PostgreSQL
```

Business logic is never duplicated between web views, API views, Celery tasks or Electron — all call the same services/selectors.

## Cross-cutting platform
`common` (base models, exceptions, utils, mixins), `accounts`, `theme`, `audit`, `events`, `outbox`, `jobs`, `health`, `api`.

## Rules
* CBV-only for web views (enforced by `tests/unit/test_foundation.py::test_cbv_only_views`).
* Services own transactions (`@transactional` / `transaction.atomic()`); selectors are read-only.
* UUID primary keys + immutable human-readable `code` fields.
* `User ≠ Employee`, `Candidate ≠ Employee`.
* Electron talks only to the REST API.
* Out of scope: AI, payroll, attendance, leave, D365, accounting, benefits, performance, learning.

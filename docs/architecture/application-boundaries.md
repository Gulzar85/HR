# Application Boundaries

| Layer | Apps | Responsibility |
|---|---|---|
| common | `common` | Base models, exceptions, utils, mixins, validators. Imports no other app. |
| platform | `accounts`, `theme`, `settings`, `feature_flags`, `audit`, `events`, `outbox`, `jobs` | Cross-cutting capabilities. |
| domain | `organizations`, `employees`, `employment`, `positions`, `assignments`, `lifecycle`, `onboarding`, `offboarding`, `movements`, `documents`, `workflows`, `approvals`, `notifications`, `hr_cases`, `headcount`, `recruitment`, `reports`, `dashboards`, `search`, `imports`, `data_quality` | Business domains. |
| interface | `api`, `health` | Transport. |

## Planned structure of every domain app
`models/ services/ selectors/ views/ forms/ permissions/ validators/ filters.py urls.py admin.py apps.py signals.py tests/` — logic never lives in `models.py`, `views.py`, `forms.py` or `admin.py`.

## Employee domain (documented, built in Phases 3–5)
```
Person → Employee → Employment → Assignment → Organization / Position / Manager
```
* **Person**: identity (name, DOB, national id, contact).
* **Employee**: the worker record in the company (code `EMP-…`), nullable link to a `User`.
* **Employment**: contract/status periods (effective-dated).
* **Assignment**: effective-dated link to organization unit, position and manager.
Keep each small; no 100-field Employee.

## Recruitment / ATS (Phase 7)
Candidate, Job Requisition, Job Posting, Application, Application Stage, Interview, Interview Panel, Assessment, Offer, Candidate Note, Recruitment Source, Hiring. `Candidate ≠ Employee`: a candidate becomes an employee only through `HireService`, which (in one transaction) creates Person/Employee/Employment/Assignment, emits `EmployeeHired`, and triggers onboarding via the outbox.

## Organization hierarchy (Phase 2)
Company → Corporate → (Lahore | Karachi) → Finance/HR/IT/Supply Chain/Corporate Ops; Company → Operations → Region → Area → Restaurant.

Other domains reference each other by ID/service/event, not by importing views.

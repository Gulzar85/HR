# McDonald's Pakistan — Employee Management System (EMS)

Enterprise EMS built as a Django **modular monolith** with a REST API for future Electron/mobile clients.

## Scope
In scope: employee lifecycle, recruitment/ATS, onboarding/offboarding, transfers/promotions, assignments, documents, workflows/approvals, HR cases, headcount, reports/dashboards, notifications, audit, data quality, imports, dynamic theme engine.
**Out of scope:** AI, payroll, attendance, leave, D365 (and sync), accounting, benefits, performance, learning.

## Stack
Python 3.12+ / Django 6.1 / DRF / PostgreSQL / Redis / Celery · Django templates + Tailwind v4 + Alpine.js (CSP build) + HTMX + Lucide + ApexCharts. See `../docs/architecture/dependencies.md`.

## Setup (Windows PowerShell; run from `backend/`)
```powershell
python -m venv ..\venv
..\venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env          # then edit SECRET_KEY, DATABASE_URL, REDIS_URL
npm install; npm run vendor; npm run build:css   # front-end assets
```
PostgreSQL: `createdb mcd_ems` and set `DATABASE_URL=postgres://user:pass@localhost:5432/mcd_ems`. (`sqlite:///db.sqlite3` works for quick local runs.)

## Identity & access (Phase 1)
```powershell
python manage.py migrate
python manage.py seed_identity            # example roles (editable in the UI)
python manage.py createsuperuser          # first administrator (email + username + password)
```
Sign in at `/accounts/login/` (email + password). Administration UI: `/admin/users/`, `/admin/roles/`, `/admin/groups/`; self-service `/profile/`, `/profile/sessions/`. Django admin (fallback) moved to `/django-admin/`. API: `/api/v1/auth/token/` (JWT). See `../docs/architecture/identity-and-access.md`, `../docs/security/`, `../docs/api/authentication.md`.

## Organization (Phase 2)
```powershell
python manage.py seed_organization --sample-operations   # dev only: company, Corporate/Operations, Lahore/Karachi + departments, sample regions/areas/restaurants
python manage.py validate_organization                   # data-quality checks
python manage.py organization_tree                       # print the hierarchy
```
UI at `/organizations/` (overview, structure tree, per-type screens). API at `/api/v1/organizations/`. Grant users an organization scope (Users → Access scopes) so they can see data. See `../docs/architecture/organization-management.md` and `../docs/security/organization-scopes.md`.

## Run
```powershell
python manage.py migrate
python manage.py runserver                     # http://localhost:8000/  health: /health/live/ /health/ready/  api: /api/v1/
celery -A config worker -l info --pool=solo    # --pool=solo on Windows
celery -A config beat -l info                  # schedules outbox dispatch
```

## Quality
```powershell
.\scripts\format.ps1   # ruff format + import sort
.\scripts\lint.ps1     # ruff + mypy
.\scripts\test.ps1     # pytest
.\scripts\check.ps1    # django check + migration check
```

## Layout
`config/` settings (base/development/testing/production), urls, celery · `apps/` domain apps · `templates/ static/ tests/` · `../docs` architecture, ADRs · `../desktop/electron-ems` · `../deployment` drafts.

## Architectural rules
1. CBVs only for web views. 2. Writes in services (`transaction.atomic`), reads in selectors. 3. UUID PKs + immutable business codes. 4. User ≠ Employee; Candidate ≠ Employee. 5. Electron uses only the REST API. 6. No hard-coded brand colors; use theme tokens. 7. Dependencies flow common → platform → domain → services → web/api. 8. Schema changes only via migrations. 9. Logging via `ems.*` loggers, never `print`.

Status: Phase 0 (foundation), Phase 1 (identity, RBAC, user administration) and Phase 2 (organization management) complete.

Roadmap: `../docs/architecture/phase-roadmap.md`. Each phase is committed and pushed on completion.

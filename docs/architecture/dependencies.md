# Dependencies and Why

| Package | Reason |
|---|---|
| Django 6.1 | Framework |
| djangorestframework | REST API for Electron/mobile |
| django-environ | Env-based configuration (`DATABASE_URL`, etc.) |
| psycopg[binary] | PostgreSQL driver |
| redis | Cache + health checks; Celery broker client |
| celery | Background jobs, outbox dispatch, schedules |
| django-filter | Declarative filtering (web + API) |
| django-htmx | HTMX request detection middleware |
| django-crispy-forms, crispy-tailwind | Tailwind form rendering |
| django-guardian | Object-level permissions |
| django-csp | Content-Security-Policy |
| djangorestframework-simplejwt (Phase 1) | JWT access + rotating/blacklistable refresh tokens for Electron/mobile (ADR-011); includes the `token_blacklist` app for revocation |
| django-import-export | Bulk import (Phase 18) |
| whitenoise | Static files in production |
| Dev: pytest, pytest-django, ruff, mypy, django-stubs, djangorestframework-stubs | Tests, lint+format+import sort, typing |
| npm (build only): tailwindcss, @tailwindcss/cli, htmx.org, @alpinejs/csp, lucide, apexcharts | Vendored into `static/` by `npm run vendor` / `build:css` |

- **Pillow**: verifies employee profile photo uploads (format, size and pixel limits). Added in Phase 3.

Deliberately not added: drf-spectacular, Elasticsearch/OpenSearch, an MFA library (deferred).

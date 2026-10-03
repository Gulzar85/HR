# Security Architecture

## Baseline (Phase 0)
* Secrets only from environment (`.env`, never committed).
* django-csp 4: `default-src 'self'`, nonce-based scripts/styles, `frame-ancestors 'none'`. Alpine.js uses the CSP build (no `unsafe-eval`).
* CSRF + secure/HttpOnly/SameSite cookies; HSTS, SSL redirect, nosniff, referrer policy, COOP, X-Frame-Options DENY in production.
* Password validators (min length 10), 8h sessions.
* Upload validation (`apps.common.validators.validate_upload`): allow-list, size, magic bytes.
* Separate JSON log streams: app, security, audit, celery, api. No stack traces to clients.
* API throttling and uniform error envelope.

## Authorization model (built Phase 1+)
```
Role → Permission → Organization Scope → Object-level permission (django-guardian)
```
Scope resolvers registered per model through `apps.common.permissions.register_scope_resolver`; `apply_scope` fails closed (returns none) when no resolver exists. HR Admin → all; Regional/Area/Restaurant/Department manager → their unit; Employee → own data. Rules are never hard-coded in views.

## Electron / mobile
Only via HTTPS REST API with token auth (chosen in Phase 1).

# ADR-012: Authorization must always be enforced server-side

Status: Accepted (Phase 1)

## Decision
Every view, API endpoint and service re-checks permission/scope/ownership; UI hiding is cosmetic. Unmapped API methods are denied; object lookups are owner-bound; privilege changes are guarded in services.

## Why
Hidden buttons and client-side checks are trivially bypassed by direct requests (IDOR, forged POST). Defence in depth means a bug in one layer is not a breach.

## Consequences
Security tests cover anonymous access, missing permission, IDOR, CSRF, privilege escalation and inactive accounts.

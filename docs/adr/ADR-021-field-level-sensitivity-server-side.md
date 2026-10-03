# ADR-021: Field-level sensitivity is enforced server-side

Status: Accepted (Phase 3)

## Decision
Services, selectors, serializers, filters and export evaluate permissions. The API omits restricted sections. Writing a sensitive field requires permission to read it.

## Why
Restrictions applied only in templates leak through HTMX partials, the API, filters and exports.

## Consequences
There are more checks, and tests cover each read path.

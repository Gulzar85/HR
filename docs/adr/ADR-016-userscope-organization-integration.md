# ADR-016: UserScope integrates with Organization without coupling Accounts to Organizations

Status: Accepted (Phase 2)

## Decision
`accounts` keeps generic `(scope_type, scope_ref)` scopes and a callback registry. `organizations` registers each type with descendants, ancestors, validator, normalizer and describe callbacks in `AppConfig.ready()`. Domain querysets are filtered with hierarchical lookups (`hierarchy.scope_lookups`) resolved by SQL joins.

## Why
Accounts is a platform module that later domains depend on. Importing Organizations into it would invert the dependency direction and create cycles. A registry keeps the Phase 1 API unchanged and allowed Phase 2 to plug in without migrations in accounts.

## Consequences
Scope refs are unit UUIDs (stable across renames). Admins can enter codes, which are normalised. New units are covered automatically by ancestor scopes.

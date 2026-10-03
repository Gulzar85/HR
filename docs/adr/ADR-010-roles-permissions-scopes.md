# ADR-010: Roles, permissions and scopes are separate concepts

Status: Accepted (Phase 1)

## Decision
Permission = capability (Django permission). Role = admin-managed permission set. Group = set of users. Scope = where permissions apply. Object permission = per-record exception (guardian).

## Why
Merging them (for example roles that embed region logic) makes every org change a code change and explodes the number of roles. Keeping them orthogonal lets HR create roles in the UI and Phase 2 attach org units without touching permissions.

## Consequences
Scopes are generic `(type, ref)` strings with a registry, so Organization (Phase 2) integrates without migrations in accounts.

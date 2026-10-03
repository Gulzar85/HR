# ADR-009: Authentication and authorization are centralized

Status: Accepted (Phase 1)

## Decision
All identity operations go through `AuthenticationService`, `UserService`, `RoleService`, `PermissionService`, `ScopeService`, `SessionService`; reads through selectors; authorization checks through `PermissionService`/`ScopeService`/`HasPerm`.

## Why
Scattered `if user.is_manager` checks cannot be audited or changed safely. One place gives consistent rules (self-change ban, escalation guard), audit and transactions for web, API, tasks and Electron.

## Consequences
Future modules call the contract in docs/architecture/identity-and-access.md; code review rejects ad-hoc role checks.

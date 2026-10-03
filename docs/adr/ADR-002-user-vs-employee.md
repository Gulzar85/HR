# ADR-002: User and Employee are separate

Status: Accepted (Phase 0)

## Decision
`accounts.User` (login identity) has no link to employees; the Employee side holds a nullable link to User.

## Why
System users (admins, service accounts) need not be employees, and many employees (restaurant crew) will never log in. Coupling them forces fake records or unusable accounts.

## Consequences
Employee onboarding may optionally provision a User; deactivating a User never affects employment.

# ADR-008: User is separate from Employee

Status: Accepted (Phase 1)

## Decision
Authentication identity (`accounts.User`) carries no employee, organization or position data. Phase 3 adds a nullable link from Employee to User.

## Why
Administrators and service accounts are users without employment; most restaurant crew will never log in. Coupling them forces placeholder records or unusable logins and leaks HR data into the auth table. Complements ADR-002.

## Consequences
Authorization must not read employee attributes from User; org-aware access is expressed through scopes. Login identifier is email; employee code is never used to sign in.

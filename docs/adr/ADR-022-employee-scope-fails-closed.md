# ADR-022: Employee access is scope-checked and fails closed

Status: Accepted (Phase 3)

## Decision
Every read goes through `visible_employees(user)`. In Phase 3 only global-scope users and superusers can see employees; Phase 4 registers an organization-based resolver. Out-of-scope and cross-employee child records return 404.

## Why
Permissions alone cannot limit a manager to their own restaurants. Until assignments exist, the narrow default is the safe one.

## Consequences
Restaurant-level roles see no employees until Phase 4. This is intentional.

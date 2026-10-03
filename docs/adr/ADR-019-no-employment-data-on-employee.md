# ADR-019: Employee holds no organization, position, manager or pay data

Status: Accepted (Phase 3)

## Decision
This data belongs in effective-dated records in later `employment`, `positions` and `assignments` apps that reference `Employee`.

## Why
It changes over time and needs history and approvals. Columns on the master record would lose that history and couple unrelated domains.

## Consequences
Until Phase 4 there is no organization-based employee scope (see ADR-022).

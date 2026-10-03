# ADR-017: Organization hierarchy is resolved by services rather than hard-coded in views

Status: Accepted (Phase 2)

## Decision
Parent and child rules, paths, the tree, scope lookups, cascading selects and status integrity all derive from `ORG_TYPES` and the organization services and selectors. Views, templates and the API only render what those return.

## Why
Hard-coding the hierarchy in templates or views creates parallel copies that drift and cannot be authorised consistently.

## Consequences
The tree is built from the database in a fixed number of queries (one per level). Templates render generic structures. Changing the hierarchy is a code change in one module, reviewed with an ADR.

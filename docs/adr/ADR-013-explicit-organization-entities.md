# ADR-013: Organization hierarchy uses explicit domain entities

Status: Accepted (Phase 2)

## Decision
Company, Division, CorporateLocation, Department, Region, Area and Restaurant are separate models, each with one typed parent FK (PROTECT). The structure is declared once in `organizations/hierarchy.py`. Division `structure_type` (CORPORATE/OPERATIONS) decides which branch a division hosts.

## Why
A single generic Organization table, with a nullable FK per level or an adjacency list, loses type-specific fields (restaurant coordinates, department short codes) and moves validation out of the database. It also makes invalid shapes such as a restaurant under a department easy to create. Explicit entities match the locked business hierarchy and give the database real constraints.

## Consequences
Adding a level means adding a model and one `ORG_TYPES` entry. Services, selectors, scopes, the tree and the API adapt automatically. Cycles are impossible with typed FKs; `assert_not_own_ancestor` keeps the rule explicit.

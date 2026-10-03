# ADR-001: Modular monolith

Status: Accepted (Phase 0)

## Decision
One deployable Django project split into independent domain apps with enforced dependency direction.

## Why
Microservices would add operational cost (networking, distributed transactions) with no demonstrated need for a single-company HR system; one giant app would become unmaintainable.

## Consequences
Boundaries are enforced by layering rules and tests, so any module can later be extracted by replacing service calls with API/event calls.

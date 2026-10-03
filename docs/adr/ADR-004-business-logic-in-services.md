# ADR-004: Business logic lives in services

Status: Accepted (Phase 0)

## Decision
Writes go through services (transactional), reads through selectors; views/API/tasks only adapt I/O.

## Why
Prevents duplication across web, REST, Celery and Electron, and gives one place for transactions, audit and events.

## Consequences
Enforced by documentation, code review and architecture tests.

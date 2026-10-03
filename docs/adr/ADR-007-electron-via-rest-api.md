# ADR-007: Electron communicates through the REST API

Status: Accepted (Phase 0)

## Decision
The desktop client uses HTTPS + `/api/v1/` only.

## Why
Direct DB/ORM/Redis/Celery access would bypass authorization, audit and services and make the desktop app a security liability.

## Consequences
API is versioned and exposes the same services used by the web UI.

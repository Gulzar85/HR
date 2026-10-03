# ADR-014: Organization business codes are immutable

Status: Accepted (Phase 2)

## Decision
Each unit gets a generated, unique code (`CMP-001`, `DIV-OPS-001`, `LOC-LHR-001`, `DEPT-LHR-HR`, `REG-001`, `AREA-001`, `RST-LHR-001`) that never changes, including after renames or moves. `BusinessCodeModel` refuses changes on save.

## Why
Codes appear in reports, exports, integrations and people's memory. Changing them silently breaks references and audit trails. UUIDs stay the technical keys (ADR-003).

## Consequences
A code can describe where a unit started (for example `DEPT-LHR-LEG` after moving to Karachi). Corrections mean archiving the unit and creating a new one; there is no edit path.

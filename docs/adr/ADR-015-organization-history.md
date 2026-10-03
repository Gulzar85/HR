# ADR-015: Organization changes preserve historical information

Status: Accepted (Phase 2)

## Decision
Units are never deleted. Every mutation writes `OrganizationHistory` (before/after/reason/actor/effective date) and `AuditLog`. Parent links are effective-dated in `OrganizationRelationship` with half-open intervals and exactly one open row per unit.

## Why
HR reporting needs as-of-date answers (which region a restaurant belonged to last year; which department was responsible on a date). Overwriting FKs alone would lose that.

## Consequences
The FK is the fast 'current' answer; the relationship table is the historical answer. Data-quality checks detect drift between them.

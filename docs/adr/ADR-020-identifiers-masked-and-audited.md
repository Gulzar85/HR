# ADR-020: Identifiers are masked by default and revealed only explicitly

Status: Accepted (Phase 3)

## Decision
Identifiers are always rendered masked. Revealing one requires `view_identifiers` and `view_sensitive_identity` plus an explicit action. Each reveal is audited and recorded on the timeline. Audit rows never store identifier values.

## Why
CNIC and passport numbers enable identity fraud, so each view must be deliberate and traceable.

## Consequences
Search matches identifiers only by exact value, and only for users permitted to see identifiers.

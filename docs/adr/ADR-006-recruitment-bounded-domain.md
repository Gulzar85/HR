# ADR-006: Recruitment/ATS is a separate bounded domain

Status: Accepted (Phase 0)

## Decision
`apps/recruitment` owns candidates and hiring pipeline; Candidate ≠ Employee; hire happens only via `HireService`.

## Why
Candidates have a different lifecycle, data-protection posture and volume than employees; mixing them pollutes employee data.

## Consequences
Recruitment never writes employee tables directly; onboarding starts from an `EmployeeHired` event.

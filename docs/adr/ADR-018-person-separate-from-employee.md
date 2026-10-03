# ADR-018: Person is separate from Employee

Status: Accepted (Phase 3)

## Decision
Human identity lives on `Person`. `Employee` is a thin one-to-one record holding the code, status and an optional user link.

## Why
Candidates, dependants and contacts are people who are not employees. Re-hiring someone must not duplicate their identity.

## Consequences
Recruitment can create a `Person` and promote it later. Employee queries use `select_related("person")`.

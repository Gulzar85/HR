# ADR-003: UUID primary keys + business codes

Status: Accepted (Phase 0)

## Decision
Technical PK is UUID; humans use separate unique, immutable `code` fields (EMP-000001, TRF-2026-000001) from `CodeSequence`.

## Why
UUIDs are safe in URLs/APIs/offline clients and merge-friendly; business codes are readable in reports and support desks. Names are never identifiers.

## Consequences
`BusinessCodeModel` blocks code changes; `generate_code` is row-locked for concurrency.

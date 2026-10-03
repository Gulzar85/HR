# ADR-005: Theme Engine is a first-class module

Status: Accepted (Phase 0)

## Decision
Branding (logo, colors, typography, modes) is data-driven and delivered as semantic CSS variables.

## Why
Avoids brand colors baked into templates; supports light/dark/system and future per-unit branding without redeploys.

## Consequences
Templates use tokens only; the engine ships services in Phase 0 and models in Phase 6.

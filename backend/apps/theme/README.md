# Theme (Dynamic Theme Engine)

First-class platform module. Phase 0 ships services + context processor only (no models).

Planned models (Phase 6): `Theme`, `ThemeVariable`, `ThemeComponent`, `ThemeAsset`, `ThemeAssignment`.
Templates use semantic tokens only (`bg-(--color-surface)`, `text-(--color-text)`); never hex values.
See `docs/architecture/theme-engine.md`.

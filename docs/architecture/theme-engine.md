# Theme Engine

First-class platform module (`apps/theme`). Phase 0: services, CSS-variable renderer, context processor. Phase 6: DB models + admin UI.

Planned models: `Theme`, `ThemeVariable`, `ThemeComponent`, `ThemeAsset`, `ThemeAssignment` (global → company → org unit → user).

Services: `ThemeService.resolve(request)`, `render_css_variables(theme)`, `ThemeAssetService.url(kind)`; context processor exposes `theme`, `theme_css`, `theme_logo_url`, `theme_favicon_url`.

## Semantic tokens
`--color-primary --color-secondary --color-accent --color-background --color-surface --color-text --color-muted --color-border --color-success --color-warning --color-danger --color-info --radius --font-sans`; modes light / dark / system (dark overrides emitted under `prefers-color-scheme` for system).

Templates never contain brand hex values (`bg-[#DA291C]`); use `bg-(--color-primary)` (Tailwind v4) or the classes in `static/css/ems.css`. Emitted values are validated against a safe pattern before rendering.

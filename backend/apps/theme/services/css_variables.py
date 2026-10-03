"""Render a resolved theme into semantic CSS custom properties (--color-primary, ...)."""

from __future__ import annotations

import re

from .theme_service import ResolvedTheme

_SAFE_NAME = re.compile(r"^[a-z0-9-]+$")
_SAFE_VALUE = re.compile(r"^[#a-zA-Z0-9\s.,%()'\"_/-]+$")


def _decls(tokens: dict[str, str]) -> str:
    lines = []
    for name, value in sorted(tokens.items()):
        if not _SAFE_NAME.match(name) or not _SAFE_VALUE.match(value):
            continue  # never emit unvalidated CSS
        lines.append(f"  --{name}: {value};")
    return "\n".join(lines)


def render_css_variables(theme: ResolvedTheme) -> str:
    css = f":root {{\n{_decls(theme.tokens)}\n}}\n"
    dark = _decls(theme.dark_tokens)
    if dark and theme.mode in ("dark", "system"):
        if theme.mode == "dark":
            css += f":root {{\n{dark}\n}}\n"
        else:
            css += f"@media (prefers-color-scheme: dark) {{\n:root {{\n{dark}\n}}\n}}\n"
    return css

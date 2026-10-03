"""Theme resolution.

Phase 0: resolves the built-in default theme from ``settings.EMS_THEME_DEFAULTS``.
Phase 6: resolves via ThemeAssignment (global -> company -> org unit -> user) from the DB,
falling back to the defaults. Callers (context processor, CSS endpoint) do not change.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class ResolvedTheme:
    brand_name: str
    tagline: str
    mode: str  # light | dark | system
    tokens: dict[str, str] = field(default_factory=dict)
    dark_tokens: dict[str, str] = field(default_factory=dict)
    assets: dict[str, str] = field(default_factory=dict)  # logo / icon / favicon URLs


class ThemeService:
    @staticmethod
    def resolve(request: Any = None) -> ResolvedTheme:
        d: dict[str, Any] = copy.deepcopy(settings.EMS_THEME_DEFAULTS)
        return ResolvedTheme(
            brand_name=d["brand_name"],
            tagline=d["tagline"],
            mode=d["mode"],
            tokens=d["tokens"],
            dark_tokens=d["dark_tokens"],
        )

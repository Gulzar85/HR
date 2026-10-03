"""Theme asset lookup (logo, icon, favicon). DB-backed ThemeAsset arrives in Phase 6."""

from __future__ import annotations

from django.templatetags.static import static


class ThemeAssetService:
    DEFAULTS = {"logo": "img/logo.svg", "favicon": "img/favicon.svg"}

    @classmethod
    def url(cls, kind: str) -> str:
        return static(cls.DEFAULTS[kind])

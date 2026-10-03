"""UI preferences are a closed set of keys with validated values (no free-form JSON)."""

from __future__ import annotations

from typing import Any

from apps.common.exceptions import ValidationException

THEME_MODES = ("system", "light", "dark")
ALLOWED_KEYS = {"theme_mode"}


def clean_preferences(data: dict[str, Any]) -> dict[str, Any]:
    unknown = set(data) - ALLOWED_KEYS
    if unknown:
        raise ValidationException(f"Unknown preference(s): {', '.join(sorted(unknown))}.")
    if "theme_mode" in data and data["theme_mode"] not in THEME_MODES:
        raise ValidationException("Invalid theme mode.")
    return dict(data)

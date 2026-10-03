"""Business-code generation.

Formats (examples): EMP-000001, RST-LHR-001, TRF-2026-000001.
Domain apps call ``generate_code`` from their services; they own their prefixes.
"""

from __future__ import annotations

from django.db import transaction

from apps.common.models.codes import CodeSequence


def generate_code(
    prefix: str,
    *,
    scope: str = "",
    year: int | None = None,
    width: int = 6,
) -> str:
    """Return the next code for (prefix, scope, year). Concurrency-safe (row lock)."""
    with transaction.atomic():
        seq, _ = CodeSequence.objects.select_for_update().get_or_create(
            prefix=prefix, scope=scope, year=year or 0
        )
        seq.last_value += 1
        seq.save(update_fields=["last_value"])
    parts = [prefix]
    if scope:
        parts.append(scope)
    if year:
        parts.append(str(year))
    parts.append(f"{seq.last_value:0{width}d}")
    return "-".join(parts)

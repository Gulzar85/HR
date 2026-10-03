"""API response conventions.

Success: ``{"data": ..., "meta": {...}}``   Error: ``{"error": {"code", "message", "details"}}``
Paginated lists use DRF's StandardPagination (count/next/previous/results).
"""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response


def success(data: Any = None, *, meta: dict[str, Any] | None = None, status: int = 200) -> Response:
    return Response({"data": data, "meta": meta or {}}, status=status)


def error_payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}

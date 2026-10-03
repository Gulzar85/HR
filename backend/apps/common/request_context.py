"""Request metadata passed from views/API into services (IP, user agent, base URL).

Services never receive ``HttpRequest``; they receive this small immutable value object so the
same service works from web views, API views and Celery tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings


def get_client_ip(request: Any) -> str | None:
    """Client IP. ``X-Forwarded-For`` is only honoured behind N trusted proxies (default 0)."""
    trusted = getattr(settings, "EMS_TRUSTED_PROXY_COUNT", 0)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if trusted and forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if len(hops) >= trusted:
            return hops[-trusted]
    return request.META.get("REMOTE_ADDR") or None


@dataclass(frozen=True)
class RequestContext:
    ip_address: str | None = None
    user_agent: str = ""
    base_url: str = ""

    @classmethod
    def from_request(cls, request: Any | None) -> RequestContext:
        if request is None:
            return cls(base_url=getattr(settings, "EMS_SITE_URL", ""))
        base_url = getattr(settings, "EMS_SITE_URL", "")
        if not base_url:
            try:
                base_url = f"{request.scheme}://{request.get_host()}"
            except Exception:  # synthetic requests (e.g. test login helpers) may lack host info
                base_url = ""
        return cls(
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:400],
            base_url=base_url,
        )


SYSTEM_CONTEXT = RequestContext()

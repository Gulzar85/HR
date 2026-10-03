"""Translate uncaught DomainException into a consistent HTML error response (web only).

API requests are handled by ``apps.api.exceptions.api_exception_handler`` inside DRF.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .exceptions import DomainException
from .logging import get_logger

logger = get_logger("app")


class DomainExceptionMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(self, request: HttpRequest, exception: Exception) -> HttpResponse | None:
        if not isinstance(exception, DomainException):
            return None
        if request.path.startswith("/api/"):
            return None
        logger.info("domain_exception", extra={"code": exception.code, "path": request.path})
        return render(
            request,
            "errors/domain_error.html",
            {"error": exception.to_dict(), "status": exception.http_status},
            status=exception.http_status,
        )

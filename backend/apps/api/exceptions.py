"""DRF exception handler: consistent error envelope, domain exceptions mapped, no stack traces."""

from __future__ import annotations

from rest_framework import exceptions as drf
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.common.exceptions import DomainException
from apps.common.logging import get_logger

from .responses import error_payload

logger = get_logger("api")


def api_exception_handler(exc, context):
    if isinstance(exc, DomainException):
        return Response(error_payload(exc.code, exc.message, exc.details), status=exc.http_status)

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("api_unhandled_exception")
        return Response(error_payload("server_error", "An unexpected error occurred."), status=500)

    if isinstance(exc, drf.ValidationError):
        code, message, details = "validation_error", "The submitted data is invalid.", response.data
    else:
        code = getattr(exc, "default_code", "error")
        message = str(getattr(exc, "detail", "Error"))
        details = {}
    response.data = error_payload(str(code), message, details)
    return response

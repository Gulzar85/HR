"""Domain exception hierarchy.

Services raise these; the web middleware and the DRF exception handler translate them
into consistent HTML / JSON responses. Never raise bare ``Exception`` from a service.
"""

from __future__ import annotations

from typing import Any


class DomainException(Exception):
    """Base class for all expected, business-level errors."""

    default_message = "A domain error occurred."
    default_code = "domain_error"
    http_status = 400

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class ValidationException(DomainException):
    default_message = "The submitted data is invalid."
    default_code = "validation_error"
    http_status = 400


class PermissionDeniedException(DomainException):
    default_message = "You do not have permission to perform this action."
    default_code = "permission_denied"
    http_status = 403


class NotFoundException(DomainException):
    default_message = "The requested resource was not found."
    default_code = "not_found"
    http_status = 404


class ConflictException(DomainException):
    default_message = "The operation conflicts with the current state."
    default_code = "conflict"
    http_status = 409


class BusinessRuleException(DomainException):
    default_message = "A business rule was violated."
    default_code = "business_rule_violation"
    http_status = 422

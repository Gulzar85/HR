from __future__ import annotations

from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError

from apps.common.exceptions import ValidationException


def validate_new_password(password: str, user=None) -> None:
    """Run the configured AUTH_PASSWORD_VALIDATORS; raise a domain ValidationException."""
    try:
        django_validate_password(password, user)
    except ValidationError as exc:
        raise ValidationException(
            "The password does not meet the requirements.", details={"password": list(exc.messages)}
        ) from exc

"""Employee-domain field validators.

Reusable across forms, services, models and the DRF layer so a rule is written once. Age limits and
upload policy are read from settings (never hard-coded per form) - see docs/security/employee-data.md.
"""

from __future__ import annotations

import re
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from ..models.reference import country_codes, validate_nationality  # noqa: F401  (re-export)

# Leading-bytes signatures. The extension alone is never trusted.
IMAGE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
}

IMAGE_FORMATS = {"JPEG", "PNG", "GIF", "WEBP"}


# --------------------------------------------------------------------------- dates & ages
def age_on(dob: date, on: date | None = None) -> int:
    """Completed years between ``dob`` and ``on`` (default: today, local timezone)."""
    on = on or timezone.localdate()
    years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    return years


def min_employee_age() -> int:
    """Lowest age an employee may be (settings-driven, not duplicated per form).

    **Not** a person rule. A person may be any age; whether someone may be *employed* is decided by
    the Employment/Lifecycle modules in Phase 4+, which call :func:`assert_old_enough_to_employ`.
    Phase 3 only needs the number available to them.
    """
    return int(getattr(settings, "EMS_MIN_EMPLOYEE_AGE", 14))


def max_employee_age() -> int:
    """Age beyond which a date of birth is treated as a data-entry error."""
    return int(getattr(settings, "EMS_MAX_EMPLOYEE_AGE", 120))


def validate_date_of_birth(value: date | None) -> None:
    """Reject future dates and implausible ages - the *identity* rules for a ``Person``.

    Two checks only, and deliberately no minimum age: personhood has no age floor, and imposing one
    here would refuse to record a child, an apprentice or a job applicant. Employment eligibility
    belongs to Phase 4.
    """
    if value is None:
        return
    today = timezone.localdate()
    if value > today:
        raise ValidationError("Date of birth cannot be in the future.", code="dob_future")
    years = age_on(value, today)
    if years > max_employee_age():
        raise ValidationError(
            f"Date of birth looks incorrect (over {max_employee_age()} years).", code="dob_too_old"
        )


def assert_old_enough_to_employ(value: date | None) -> None:
    """Phase 4+ helper: the minimum-employment-age rule, kept out of the person identity path."""
    if value is None:
        return
    years = age_on(value, timezone.localdate())
    if years < min_employee_age():
        raise ValidationError(
            f"Employee must be at least {min_employee_age()} years old.", code="dob_too_young"
        )


# ------------------------------------------------------------------------------- uploads
def validate_profile_photo(file) -> None:
    """Size + extension allow-list + magic bytes + full image decode for a profile photo.

    Nothing is trusted from the client: the filename extension only selects which signature to
    expect, the decoded image decides whether the file really is a picture, and anything that is not
    an image format on the allow-list is rejected outright (no SVG - it can carry script).
    """
    if not file:
        return
    max_bytes = int(getattr(settings, "EMS_PROFILE_PHOTO_MAX_BYTES", 2 * 1024 * 1024))
    allowed = tuple(
        ext.lower() for ext in getattr(settings, "EMS_PROFILE_PHOTO_EXTENSIONS", IMAGE_SIGNATURES)
    )
    name = getattr(file, "name", "") or ""
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in allowed:
        raise ValidationError(f"Photos must be one of: {', '.join(allowed)}.", code="photo_type")
    size = getattr(file, "size", None)
    if size is None:
        size = len(file.read())
        file.seek(0)
    if size > max_bytes:
        raise ValidationError(
            f"Photo is too large (maximum {max_bytes // (1024 * 1024)} MB).", code="photo_size"
        )
    head = file.read(16)
    file.seek(0)
    signatures = IMAGE_SIGNATURES.get(ext)
    if signatures and not any(head.startswith(sig) for sig in signatures):
        raise ValidationError(
            "Photo content does not match its file extension.", code="photo_content"
        )
    try:
        from PIL import Image  # imported lazily: only needed when a photo is actually uploaded

        image = Image.open(file)
        image.verify()
        if (image.format or "").upper() not in IMAGE_FORMATS:
            raise ValidationError(
                f"Unsupported image format '{image.format}'.", code="photo_format"
            )
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 - any decoder failure means "not a valid image"
        raise ValidationError(
            "The uploaded file is not a readable image.", code="photo_invalid"
        ) from exc
    finally:
        file.seek(0)


def profile_photo_widget_attrs() -> dict[str, str]:
    accept = getattr(settings, "EMS_PROFILE_PHOTO_EXTENSIONS", tuple(IMAGE_SIGNATURES))
    return {"accept": ",".join(accept)}


# --------------------------------------------------------------------- phone / email / codes
_NON_DIGIT = re.compile(r"[^0-9+]")


def normalize_phone(value: str) -> str:
    """Digits with a single leading ``+``: the searchable form of a phone number."""
    raw = (value or "").strip()
    plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    return f"+{digits}" if plus and digits else digits


def validate_phone(value: str) -> None:
    digits = re.sub(r"\D", "", value or "")
    if not (7 <= len(digits) <= 15):  # E.164 allows at most 15 digits
        raise ValidationError("Enter a valid phone number.", code="invalid_phone")


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def validate_issuing_country(value: str) -> None:
    code = (value or "").strip().upper()
    if code == "" or code in country_codes():
        return
    raise ValidationError("Choose a country from the configured list.", code="unknown_country")

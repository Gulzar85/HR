"""Reusable validators, including the file-upload validation foundation."""

from __future__ import annotations

import os

from django.conf import settings
from django.core.exceptions import ValidationError

# Leading-bytes signatures; extension alone is not trusted.
_SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
}


def validate_upload(file) -> None:
    """Validate size, extension allow-list and magic bytes of an uploaded file."""
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in settings.EMS_UPLOAD_ALLOWED_EXTENSIONS:
        raise ValidationError(f"File type '{ext}' is not allowed.", code="file_type")
    if file.size > settings.EMS_UPLOAD_MAX_BYTES:
        raise ValidationError("File is too large.", code="file_size")
    head = file.read(16)
    file.seek(0)
    sigs = _SIGNATURES.get(ext)
    if sigs and not any(head.startswith(s) for s in sigs):
        raise ValidationError("File content does not match its extension.", code="file_content")


def validate_not_blank(value: str) -> None:
    if not value or not value.strip():
        raise ValidationError("This field may not be blank.", code="blank")

"""Backwards-compatible re-export; the mixins live in ``apps.common.views.base`` since Phase 2."""

from apps.common.views.base import (  # noqa: F401
    FORM_ERRORS,
    AdminAccessMixin,
    PostActionView,
    ServiceFormView,
)

"""Selector conventions: read-only, optimized, reusable queries. No writes, no HTTP."""

from __future__ import annotations

from typing import Generic, TypeVar

from django.db.models import Model, QuerySet

from apps.common.exceptions import NotFoundException

M = TypeVar("M", bound=Model)


class BaseSelector(Generic[M]):
    model: type[M]

    def base_queryset(self) -> QuerySet[M]:
        """Override to add select_related/prefetch_related shared by all reads."""
        return self.model._default_manager.all()

    def get_by_code(self, code: str) -> M:
        try:
            return self.base_queryset().get(code=code)
        except self.model.DoesNotExist as exc:  # type: ignore[attr-defined]
            raise NotFoundException(f"{self.model.__name__} '{code}' not found.") from exc

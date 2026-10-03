"""Pagination helpers for API (DRF) and web (Django) use."""

from __future__ import annotations

from django.core.paginator import Page, Paginator
from django.db.models import QuerySet
from rest_framework.pagination import PageNumberPagination

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


class StandardPagination(PageNumberPagination):
    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = MAX_PAGE_SIZE


def get_page(
    queryset: QuerySet, page_number: int | str | None, per_page: int = DEFAULT_PAGE_SIZE
) -> Page:
    """Paginate any queryset; invalid/out-of-range page numbers fall back safely."""
    return Paginator(queryset, min(per_page, MAX_PAGE_SIZE)).get_page(page_number)

"""Service conventions.

A service is a plain module/class exposing business operations. Rules:
* Every multi-step operation is decorated with ``@transactional`` (all-or-nothing).
* Side effects that must only happen after commit use ``after_commit``.
* Services raise ``DomainException`` subclasses; they never touch HttpRequest.
* Web views, API views, Celery tasks and Electron (through the API) all call the same services.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from django.db import transaction

F = TypeVar("F", bound=Callable[..., Any])


def transactional(func: F) -> F:
    """Run the wrapped service function inside ``transaction.atomic()``."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with transaction.atomic():
            return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def after_commit(callback: Callable[[], None]) -> None:
    """Schedule ``callback`` to run only if the surrounding transaction commits."""
    transaction.on_commit(callback)

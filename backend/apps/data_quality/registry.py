"""Data-quality check registry (platform for every domain; Phase 19 adds persistence, scheduling, UI).

Domains register checks in ``AppConfig.ready()``:

    @register_check("organizations", "ORG-INACTIVE-PARENT", "Live unit under a non-live parent")
    def inactive_parent_with_live_child() -> Iterable[Issue]: ...

A check yields ``Issue`` objects and must be read-only.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    check: str
    severity: str
    message: str
    object_type: str = ""
    object_id: str = ""
    object_code: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Check:
    domain: str
    code: str
    description: str
    severity: str
    func: Callable[[], Iterable[Issue]]


_CHECKS: dict[str, Check] = {}


def register_check(domain: str, code: str, description: str, severity: str = ERROR):
    def decorator(func: Callable[[], Iterable[Issue]]):
        _CHECKS[code] = Check(domain, code, description, severity, func)
        return func

    return decorator


def checks(domain: str | None = None) -> list[Check]:
    return [c for c in _CHECKS.values() if domain is None or c.domain == domain]


def run_checks(domain: str | None = None) -> list[Issue]:
    issues: list[Issue] = []
    for check in checks(domain):
        issues.extend(check.func())
    return issues

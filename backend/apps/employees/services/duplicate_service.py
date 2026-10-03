"""Duplicate detection - *flags*, never merges (Phase 3, docs/architecture/employee-domain.md).

Signals, cheapest first:

* the same official identifier value (CNIC/passport) on another employee - the strongest signal;
* the same primary email on another employee;
* the same primary mobile on another employee;
* the same first/last name **and** the same date of birth.

Two deliberate limits:

* **No automatic merging, and no hard block except uniqueness.** A duplicate warning tells the user
  what was found and lets them continue; only a duplicate identifier value fails, because that is a
  database constraint. Blocking creation on a shared mobile would be wrong (families share numbers).
* **Signals never leak.** A duplicate check is only ever run for an actor who may add employees, and
  the result is the *fact* of a match plus the existing employee code - never the matching value.

The persistent findings live in ``apps.data_quality`` (``EMP-POTENTIAL-DUPLICATE``). Phase 3
produces the check; the merge workflow itself is deferred (ADR-040 territory, not this phase).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db.models import Q, QuerySet

from ..models import (
    Contact,
    Employee,
    VerificationStatus,
    normalize_identifier,
)
from ..models.contact import EMAIL_TYPES

#: Signal codes, also used as data-quality issue suffixes.
SIGNAL_IDENTIFIER = "identifier"
SIGNAL_EMAIL = "email"
SIGNAL_PHONE = "phone"
SIGNAL_NAME_DOB = "name_dob"

#: Search is case-insensitive on names, so a two-character name would match far too much. Any
#: term shorter than this is ignored rather than producing noise.
MIN_TERM_LENGTH = 3

#: Never look at more than this many candidates per signal - the report is a hint, not a search.
MAX_PER_SIGNAL = 5


@dataclass(frozen=True)
class DuplicateMatch:
    """One existing employee that looks like the same person."""

    employee: Any
    signal: str
    detail: str = ""

    @property
    def code(self) -> str:
        return self.employee.code

    @property
    def name(self) -> str:
        return self.employee.display_name


@dataclass
class DuplicateReport:
    matches: list[DuplicateMatch] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.matches)

    def __len__(self) -> int:
        return len(self.matches)

    def __iter__(self):
        return iter(self.matches)

    @property
    def signals(self) -> list[str]:
        return sorted({m.signal for m in self.matches})

    def by_signal(self, signal: str) -> list[DuplicateMatch]:
        return [m for m in self.matches if m.signal == signal]

    def employees(self) -> QuerySet:
        return Employee.objects.filter(pk__in={m.employee.pk for m in self.matches})

    def blocking(self) -> list[DuplicateMatch]:
        """Matches caused by a hard uniqueness rule - creation must fail for these."""
        return self.by_signal(SIGNAL_IDENTIFIER)


class DuplicateService:
    @classmethod
    def check(
        cls,
        *,
        person_data: dict[str, Any],
        identifiers: list[dict[str, Any]] | None = None,
        contacts: list[dict[str, Any]] | None = None,
        exclude_employee: Any = None,
        limit: int = 5,
    ) -> DuplicateReport:
        """Look for existing employees that may be the same person.

        ``person_data`` uses the same keys as ``PersonService.create_person``. Empty/too-short terms
        are skipped rather than searched.
        """
        report = DuplicateReport()
        excluded = exclude_employee.pk if exclude_employee is not None else None

        def add(employee: Any, signal: str, detail: str = "") -> None:
            if excluded is not None and employee.pk == excluded:
                return
            if any(m.employee.pk == employee.pk and m.signal == signal for m in report.matches):
                return
            report.matches.append(DuplicateMatch(employee=employee, signal=signal, detail=detail))

        for data in identifiers or []:
            if data.get("value") and data.get("identifier_type"):
                for employee in cls._by_identifier(data):
                    add(employee, SIGNAL_IDENTIFIER, str(data["identifier_type"]))
        for data in contacts or []:
            contact_type = data.get("contact_type")
            value = (data.get("value") or "").strip()
            if not value or not contact_type:
                continue
            signal = (
                SIGNAL_EMAIL if contact_type in ("email", "alternative_email") else SIGNAL_PHONE
            )
            for employee in cls._by_contact(contact_type, value):
                add(employee, signal)
        for employee in cls._by_name_and_dob(person_data):
            add(employee, SIGNAL_NAME_DOB)

        report.matches.sort(key=lambda m: (m.signal, m.code))
        del report.matches[limit:]
        return report

    # ------------------------------------------------------------------------- signals
    @staticmethod
    def _by_identifier(data: dict[str, Any]) -> list[Employee]:
        value = normalize_identifier(data["value"])
        if not value:
            return []
        return list(
            Employee.objects.filter(
                identifiers__identifier_type=data["identifier_type"],
                identifiers__normalized_value=value,
            )
            .exclude(identifiers__verification_status=VerificationStatus.REJECTED)
            .select_related("person")
            .distinct()[:MAX_PER_SIGNAL]
        )

    @staticmethod
    def _by_contact(contact_type: str, value: str) -> list[Employee]:
        normalized = Contact.normalize(contact_type, value)
        if not normalized:
            return []
        qs = Employee.objects.filter(
            contacts__contact_type=contact_type, contacts__normalized_value=normalized
        ).select_related("person")
        if contact_type not in EMAIL_TYPES:
            # Compare the last 7 digits so +92 300 1234567 and 0300-1234567 match.
            digits = normalized.lstrip("+")
            qs = qs.filter(
                Q(contacts__normalized_value=normalized)
                | Q(contacts__normalized_value__iendswith=digits[-7:])
            )
        return list(qs.distinct()[:MAX_PER_SIGNAL])

    @staticmethod
    def _by_name_and_dob(person_data: dict[str, Any]) -> list[Employee]:
        first = (person_data.get("first_name") or "").strip()
        last = (person_data.get("last_name") or "").strip()
        dob = person_data.get("date_of_birth")
        if dob is None or len(first) < MIN_TERM_LENGTH or len(last) < MIN_TERM_LENGTH:
            return []
        return list(
            Employee.objects.filter(
                person__first_name__iexact=first,
                person__last_name__iexact=last,
                person__date_of_birth=dob,
            ).select_related("person")[:MAX_PER_SIGNAL]
        )

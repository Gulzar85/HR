"""Employee data-quality checks, registered into ``apps.data_quality`` (no second framework).

Findings identify records by employee code only - never by the duplicated CNIC/email/phone value -
so the findings list does not itself leak sensitive data. Nothing is merged automatically: a
controlled merge workflow is future work (docs/architecture/employee-domain.md).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from django.db.models import Count, Q
from django.db.models.functions import Lower

from apps.common.utils import today_local
from apps.data_quality.registry import ERROR, WARNING, Issue, register_check

from .models import (
    Address,
    Contact,
    ContactType,
    EmergencyContact,
    Employee,
    EmployeeIdentifier,
    Person,
    VerificationStatus,
)
from .validators import max_employee_age


def _codes(employee_ids) -> dict:
    return dict(Employee.objects.filter(pk__in=list(employee_ids)).values_list("pk", "code"))


def _emp_issue(check: str, severity: str, message: str, employee_id, code: str, **details) -> Issue:
    return Issue(check, severity, message, "employee", str(employee_id), code, details)


@register_check(
    "employees", "EMP-DUPLICATE-IDENTIFIER", "Same identifier on more than one employee"
)
def duplicate_identifiers() -> Iterable[Issue]:
    groups = (
        EmployeeIdentifier.objects.exclude(verification_status=VerificationStatus.REJECTED)
        .values("identifier_type", "issuing_country", "normalized_value")
        .annotate(n=Count("employee", distinct=True))
        .filter(n__gt=1)
    )
    for g in groups:
        rows = EmployeeIdentifier.objects.filter(
            identifier_type=g["identifier_type"],
            issuing_country=g["issuing_country"],
            normalized_value=g["normalized_value"],
        ).values_list("employee_id", flat=True)
        codes = _codes(rows)
        for emp_id, code in codes.items():
            yield _emp_issue(
                "EMP-DUPLICATE-IDENTIFIER", ERROR,
                f"{code} shares a {g['identifier_type']} with {', '.join(c for c in codes.values() if c != code)}.",
                emp_id, code, identifier_type=g["identifier_type"],
            )  # fmt: skip


def _shared_contacts(contact_types, check: str, label: str) -> Iterable[Issue]:
    groups = (
        Contact.objects.filter(contact_type__in=contact_types)
        .values("normalized_value")
        .annotate(n=Count("employee", distinct=True))
        .filter(n__gt=1)
    )
    for g in groups:
        emp_ids = Contact.objects.filter(
            contact_type__in=contact_types, normalized_value=g["normalized_value"]
        ).values_list("employee_id", flat=True)
        codes = _codes(emp_ids)
        for emp_id, code in codes.items():
            others = ", ".join(c for c in codes.values() if c != code)
            yield _emp_issue(
                check,
                WARNING,
                f"{code} shares an {label} with {others} (possible duplicate).",
                emp_id,
                code,
            )


@register_check("employees", "EMP-DUPLICATE-EMAIL", "Same email on more than one employee", WARNING)
def duplicate_emails() -> Iterable[Issue]:
    yield from _shared_contacts(
        [ContactType.EMAIL, ContactType.ALTERNATIVE_EMAIL], "EMP-DUPLICATE-EMAIL", "email address"
    )


@register_check(
    "employees", "EMP-DUPLICATE-PHONE", "Same phone number on more than one employee", WARNING
)
def duplicate_phones() -> Iterable[Issue]:
    yield from _shared_contacts(
        [ContactType.MOBILE, ContactType.PHONE], "EMP-DUPLICATE-PHONE", "phone number"
    )


@register_check(
    "employees",
    "EMP-POSSIBLE-DUPLICATE",
    "Same name and date of birth on different employees",
    WARNING,
)
def same_name_and_dob() -> Iterable[Issue]:
    groups = (
        Employee.objects.filter(person__date_of_birth__isnull=False)
        .annotate(fn=Lower("person__first_name"), ln=Lower("person__last_name"))
        .values("fn", "ln", "person__date_of_birth")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
    )
    for g in groups:
        rows = Employee.objects.filter(
            person__first_name__iexact=g["fn"],
            person__last_name__iexact=g["ln"],
            person__date_of_birth=g["person__date_of_birth"],
        ).values_list("pk", "code")
        codes = dict(rows)
        for emp_id, code in codes.items():
            others = ", ".join(c for c in codes.values() if c != code)
            yield _emp_issue(
                "EMP-POSSIBLE-DUPLICATE",
                WARNING,
                f"{code} has the same name and date of birth as {others}.",
                emp_id,
                code,
            )


@register_check("employees", "EMP-INVALID-DOB", "Date of birth in the future or implausibly old")
def invalid_dates_of_birth() -> Iterable[Issue]:
    today = today_local()
    oldest = today.replace(year=today.year - max_employee_age())
    bad = Person.objects.filter(Q(date_of_birth__gt=today) | Q(date_of_birth__lt=oldest))
    for person in bad.select_related("employee"):
        emp = getattr(person, "employee", None)
        yield Issue("EMP-INVALID-DOB", ERROR, f"{emp.code if emp else person.pk} has an invalid date of birth.",
                    "employee" if emp else "person", str(emp.pk if emp else person.pk), emp.code if emp else "")  # fmt: skip


@register_check(
    "employees",
    "EMP-MULTIPLE-PRIMARY",
    "More than one primary contact/address/emergency contact of a kind",
)
def multiple_primaries() -> Iterable[Issue]:
    """Constraints prevent this; the check guards data loaded around the services."""
    sources = [
        (Contact, ["employee", "contact_type"], "contact"),
        (Address, ["employee", "address_type"], "address"),
        (EmergencyContact, ["employee"], "emergency contact"),
    ]
    for model, keys, label in sources:
        rows = (
            model._default_manager.filter(is_primary=True)  # type: ignore[misc]
            .values(*keys)
            .annotate(n=Count("pk"))
            .filter(n__gt=1)
        )
        for r in rows:
            code = _codes([r["employee"]]).get(r["employee"], "")
            yield _emp_issue(
                "EMP-MULTIPLE-PRIMARY",
                ERROR,
                f"{code} has more than one primary {label}.",
                r["employee"],
                code,
            )


@register_check(
    "employees", "EMP-MISSING-CONTACT", "Active employee without any primary contact", WARNING
)
def missing_contact() -> Iterable[Issue]:
    no_contact = Employee.objects.filter(employee_status="active").exclude(
        contacts__is_primary=True
    )
    for emp in no_contact.only("pk", "code"):
        yield _emp_issue(
            "EMP-MISSING-CONTACT", WARNING, f"{emp.code} has no primary contact.", emp.pk, emp.code
        )


@register_check(
    "employees", "EMP-INVALID-CONTACT", "Contacts whose stored value fails validation", WARNING
)
def invalid_contacts() -> Iterable[Issue]:
    from django.core.exceptions import ValidationError

    by_emp: dict = defaultdict(int)
    for contact in Contact.objects.only("pk", "employee_id", "contact_type", "value").iterator(
        chunk_size=2000
    ):
        try:
            contact.clean()
        except ValidationError:
            by_emp[contact.employee_id] += 1
    codes = _codes(by_emp)
    for emp_id, n in by_emp.items():
        yield _emp_issue(
            "EMP-INVALID-CONTACT",
            WARNING,
            f"{codes.get(emp_id, '')} has {n} invalid contact value(s).",
            emp_id,
            codes.get(emp_id, ""),
        )


@register_check(
    "employees",
    "EMP-INVALID-ADDRESS",
    "Addresses with inconsistent dates or several current rows of a type",
    WARNING,
)
def invalid_addresses() -> Iterable[Issue]:
    rows = (
        Address.objects.filter(effective_to__isnull=True)
        .values("employee", "address_type")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
    )
    for r in rows:
        code = _codes([r["employee"]]).get(r["employee"], "")
        yield _emp_issue(
            "EMP-INVALID-ADDRESS",
            WARNING,
            f"{code} has several open {r['address_type']} addresses.",
            r["employee"],
            code,
        )


@register_check("employees", "EMP-MISSING-CODE", "Employee without a business code")
def missing_code() -> Iterable[Issue]:
    for emp in Employee.objects.filter(Q(code="") | Q(code__isnull=True)).only("pk"):
        yield _emp_issue(
            "EMP-MISSING-CODE", ERROR, "Employee without an employee code.", emp.pk, ""
        )

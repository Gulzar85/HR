"""Domain events emitted by the employee domain (delivered via the Phase 0 outbox).

Every payload carries **identifiers only** - UUIDs, codes and enums - never model instances and never
sensitive values. A CNIC is never published on an event: subscribers get
``EmployeeIdentifierAdded(identifier_type=...)`` and read the value themselves under permission.

Declared here so later phases (Employment, Assignment, Onboarding, Offboarding, Recruitment) can
subscribe without importing this app's services. No handlers exist yet; notifications (Phase 14) and
workflows (Phase 5) are the intended consumers.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.events import DomainEvent


@dataclass(frozen=True)
class _PersonEvent(DomainEvent):
    person_id: str = ""


@dataclass(frozen=True)
class _EmployeeEvent(DomainEvent):
    employee_id: str = ""
    employee_code: str = ""


@dataclass(frozen=True)
class PersonCreated(_PersonEvent):
    event_type = "employees.person_created"


@dataclass(frozen=True)
class PersonUpdated(_PersonEvent):
    event_type = "employees.person_updated"


@dataclass(frozen=True)
class EmployeeCreated(_EmployeeEvent):
    event_type = "employees.employee_created"


@dataclass(frozen=True)
class EmployeeUpdated(_EmployeeEvent):
    event_type = "employees.employee_updated"


@dataclass(frozen=True)
class EmployeeStatusChanged(_EmployeeEvent):
    event_type = "employees.employee_status_changed"
    previous_status: str = ""
    employee_status: str = ""


@dataclass(frozen=True)
class EmployeeArchived(_EmployeeEvent):
    event_type = "employees.employee_archived"
    previous_status: str = ""
    employee_status: str = ""


@dataclass(frozen=True)
class EmployeeReactivated(_EmployeeEvent):
    event_type = "employees.employee_reactivated"
    previous_status: str = ""
    employee_status: str = ""


@dataclass(frozen=True)
class EmployeeIdentifierAdded(_EmployeeEvent):
    event_type = "employees.identifier_added"
    identifier_id: str = ""
    identifier_type: str = ""


@dataclass(frozen=True)
class EmployeeIdentifierUpdated(_EmployeeEvent):
    event_type = "employees.identifier_updated"
    identifier_id: str = ""
    identifier_type: str = ""


@dataclass(frozen=True)
class EmployeeIdentifierVerificationChanged(_EmployeeEvent):
    event_type = "employees.identifier_verification_changed"
    identifier_id: str = ""
    identifier_type: str = ""
    verification_status: str = ""


@dataclass(frozen=True)
class EmployeeContactAdded(_EmployeeEvent):
    event_type = "employees.contact_added"
    contact_id: str = ""
    contact_type: str = ""


@dataclass(frozen=True)
class EmployeeContactUpdated(_EmployeeEvent):
    event_type = "employees.contact_updated"
    contact_id: str = ""
    contact_type: str = ""


@dataclass(frozen=True)
class EmployeeAddressChanged(_EmployeeEvent):
    event_type = "employees.address_changed"
    address_id: str = ""
    address_type: str = ""


@dataclass(frozen=True)
class EmergencyContactAdded(_EmployeeEvent):
    event_type = "employees.emergency_contact_added"
    emergency_contact_id: str = ""


@dataclass(frozen=True)
class EmergencyContactUpdated(_EmployeeEvent):
    event_type = "employees.emergency_contact_updated"
    emergency_contact_id: str = ""


@dataclass(frozen=True)
class UserLinkedToEmployee(_EmployeeEvent):
    event_type = "employees.user_linked"
    user_id: str = ""


@dataclass(frozen=True)
class UserUnlinkedFromEmployee(_EmployeeEvent):
    event_type = "employees.user_unlinked"
    user_id: str = ""

"""Person / Employee core (Phase 3).

``Person`` is the human; ``Employee`` is that person's identity inside the organization
(docs/adr/ADR-018). Everything else in this package hangs off one of the two:

* ``EmployeeIdentifier`` - official identity documents (sensitive)
* ``Contact`` - phone / email channels
* ``Address`` - effective-dated postal addresses
* ``EmergencyContact`` - who to call
* ``PersonRelationship`` - controlled links between two people
* ``EmployeeNote`` - short internal notes
* ``TimelineEntry`` - the shared, append-only history foundation for later phases

Future phases add Employment, Assignment and Position. They reference ``Employee`` and never
require this package to change (docs/architecture/employee-domain.md).
"""

from .address import Address, AddressType
from .base import EmployeeOwnedRecord
from .contact import Contact, ContactType
from .emergency_contact import EmergencyContact
from .employee import (
    OPEN_STATUSES,
    SELECTABLE_STATUSES,
    STATUS_TRANSITIONS,
    Employee,
    EmployeeStatus,
)
from .employee_identifier import (
    ALWAYS_SENSITIVE_TYPES,
    OPEN_VERIFICATION_STATUSES,
    EmployeeIdentifier,
    IdentifierType,
    VerificationStatus,
    normalize_identifier,
)
from .employee_note import EmployeeNote, NoteVisibility
from .person import Person
from .reference import (
    DEFAULT_COUNTRIES,
    Gender,
    RelationshipType,
    country_choices,
    country_label,
    display_gender,
    gender_choices,
    validate_nationality,
)
from .relationship import PersonRelationship
from .timeline import TimelineEntry

__all__ = [
    "ALWAYS_SENSITIVE_TYPES",
    "DEFAULT_COUNTRIES",
    "OPEN_STATUSES",
    "OPEN_VERIFICATION_STATUSES",
    "SELECTABLE_STATUSES",
    "STATUS_TRANSITIONS",
    "Address",
    "AddressType",
    "Contact",
    "ContactType",
    "EmergencyContact",
    "Employee",
    "EmployeeIdentifier",
    "EmployeeNote",
    "EmployeeOwnedRecord",
    "EmployeeStatus",
    "Gender",
    "IdentifierType",
    "NoteVisibility",
    "Person",
    "PersonRelationship",
    "RelationshipType",
    "TimelineEntry",
    "VerificationStatus",
    "country_choices",
    "country_label",
    "display_gender",
    "gender_choices",
    "normalize_identifier",
    "validate_nationality",
]

"""Service layer for the employee domain (Phase 3).

Every write goes through one of these classes. They own authorization, validation, audit logging,
domain events and transaction boundaries, so the CBV views, the DRF API and any future integration
consumer get identical behaviour (docs/architecture/application-boundaries.md).

Rule of thumb used throughout:

* **views and serializers never write** - they call a service;
* **services never render** - they return model instances or plain data;
* **selectors never authorize** - the caller has already been authorized by the service, or is a
  read path that authorizes once up front;
* **sensitive values never enter audit rows or timeline summaries**.
"""

from .address_service import AddressService
from .base import actor_or_none, snapshot, validator_errors
from .contact_service import ContactService
from .duplicate_service import DuplicateMatch, DuplicateReport, DuplicateService
from .emergency_contact_service import EmergencyContactService
from .employee_service import CODE_PREFIX, EmployeeService
from .identifier_service import IdentifierService
from .note_service import NoteService, RelationshipService
from .person_service import PersonService
from .timeline_service import TimelineService, record_event

__all__ = [
    "CODE_PREFIX",
    "AddressService",
    "ContactService",
    "DuplicateMatch",
    "DuplicateReport",
    "DuplicateService",
    "EmergencyContactService",
    "EmployeeService",
    "IdentifierService",
    "NoteService",
    "PersonService",
    "RelationshipService",
    "TimelineService",
    "actor_or_none",
    "record_event",
    "snapshot",
    "validator_errors",
]

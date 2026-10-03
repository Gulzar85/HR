"""Shared abstract base for records that belong to an employee.

Every concrete employee-domain record inherits :class:`EmployeeOwnedRecord`, so:

* ``created_by`` / ``updated_by`` are always populated **by the service layer** (no thread-local
  magic - see ``apps.common.models.base.AuditedModel``);
* the FK from a child record to its employee always uses ``PROTECT``, because employee history is
  never discarded (ADR-022).

The ``employee`` FK itself is **declared by each concrete model**, not here. Django's
``related_name="%(class)ss"`` expands to the lower-cased class name, which would give us
``employeeidentifiers`` / ``emergencycontacts`` / ``employeenotes``. Those names are unreadable and
they leak the model name into the domain vocabulary, so each child spells out the reverse accessor the
rest of the codebase and the UI use instead: ``employee.identifiers``, ``employee.contacts``,
``employee.addresses``, ``employee.emergency_contacts``, ``employee.notes``.
"""

from __future__ import annotations

from apps.common.models import AuditedModel, UUIDModel

#: The reverse accessor names, spelled out once so the models, selectors and API cannot drift apart.
IDENTIFIERS = "identifiers"
CONTACTS = "contacts"
ADDRESSES = "addresses"
EMERGENCY_CONTACTS = "emergency_contacts"
NOTES = "notes"


class EmployeeOwnedRecord(UUIDModel, AuditedModel):
    """Abstract: a record that hangs off exactly one ``Employee``.

    Subclasses must add::

        employee = models.ForeignKey(
            "employees.Employee", on_delete=models.PROTECT, related_name=IDENTIFIERS
        )
    """

    class Meta:
        abstract = True

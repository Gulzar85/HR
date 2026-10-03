"""``Employee`` creation, immutable codes, and the boundary rules of the master record.

These are the tests that would catch the mistakes Phase 3 exists to prevent: a duplicate person, a
hand-rolled employee number, a self-referencing relationship, or a status field that starts
pretending to be an employment lifecycle.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import AuditLog
from apps.common.exceptions import (
    BusinessRuleException,
    ConflictException,
    PermissionDeniedException,
    ValidationException,
)
from apps.employees.models import Employee, EmployeeStatus, Person, TimelineEntry
from apps.employees.services import EmployeeService, PersonService
from apps.outbox.models import OutboxEvent


class TestEmployeeCreation:
    def test_creates_person_and_employee_atomically(self, hr_admin):
        person = EmployeeService.create_employee(
            actor=hr_admin,
            person_data={
                "first_name": "Ayesha",
                "last_name": "Khan",
                "date_of_birth": "1990-04-12",
            },
        )

        assert isinstance(person, Employee)
        assert person.person_id and Person.objects.filter(pk=person.person_id).exists()
        assert person.employee_status == EmployeeStatus.ACTIVE
        assert person.display_name == "Ayesha Khan"

    def test_generates_immutable_sequential_code(self, hr_admin, make_employee):
        first = make_employee(actor=hr_admin)
        second = make_employee(actor=hr_admin)

        assert re.fullmatch(r"EMP-\d{6}", first.code)
        assert re.fullmatch(r"EMP-\d{6}", second.code)
        assert first.code < second.code  # generate_code increments, never counts rows
        assert first.code != second.code

    def test_code_cannot_be_edited_by_the_update_path(self, hr_admin, employee):
        original = employee.code
        EmployeeService.update_employee(
            employee, actor=hr_admin, data={"employee_status": EmployeeStatus.INACTIVE}
        )
        employee.refresh_from_db()
        assert employee.code == original

    def test_duplicate_identifier_value_is_rejected(self, hr_admin, employee):
        """The database refuses it, not just the service - so imports cannot slip past either."""
        from apps.employees.models import normalize_identifier

        with pytest.raises(ConflictException):
            EmployeeService.create_employee(
                actor=hr_admin,
                person_data={
                    "first_name": "Clash",
                    "last_name": "Person",
                    "date_of_birth": "1995-05-05",
                },
                identifiers=[
                    {
                        "identifier_type": "cnic",
                        "value": employee.identifiers.first().value,
                        "is_primary": True,
                    }
                ],
            )

        assert normalize_identifier(
            Employee.objects.get(pk=employee.pk).identifiers.first().value
        ) == normalize_identifier(employee.identifiers.first().value)

    def test_a_rejected_identifier_may_be_re_entered(self, hr_admin, employee):
        """Rejection releases the uniqueness slot so a corrected value can be recorded."""
        from apps.employees.services import IdentifierService

        original = employee.identifiers.first()
        IdentifierService.update_identifier(
            original, actor=hr_admin, data={"verification_status": "rejected"}
        )

        second = EmployeeService.create_employee(
            actor=hr_admin,
            person_data={"first_name": "Retry", "last_name": "Case", "date_of_birth": "1995-05-05"},
            identifiers=[{"identifier_type": "cnic", "value": original.value, "is_primary": True}],
        )
        assert second.identifiers.filter(verification_status="rejected").count() == 0

    def test_rejects_a_person_who_already_is_an_employee(self, hr_admin, employee):
        with pytest.raises(ConflictException) as exc:
            EmployeeService.create_employee(
                actor=hr_admin, person=employee.person, person_data={"first_name": "X"}
            )
        assert exc.value.code == "person_already_employed"

    def test_requires_personal_information(self, hr_admin):
        with pytest.raises(ValidationException):
            EmployeeService.create_employee(actor=hr_admin)

    def test_related_records_are_created_with_the_first_as_primary(self, hr_admin):
        employee = EmployeeService.create_employee(
            actor=hr_admin,
            person_data={
                "first_name": "Multi",
                "last_name": "Record",
                "date_of_birth": "1988-08-08",
            },
            contacts=[
                {"contact_type": "mobile", "value": "+92 300 5550001"},
                {"contact_type": "mobile", "value": "+92 300 5550002"},
                {"contact_type": "email", "value": "multi@example.com"},
            ],
            emergency_contacts=[
                {"name": "One", "relationship": "parent", "phone": "0300-1234567"},
                {"name": "Two", "relationship": "other", "phone": "0300-7654321"},
            ],
        )

        mobiles = [c for c in employee.contacts.all() if c.contact_type == "mobile"]
        assert [c.is_primary for c in mobiles] == [True, False]
        assert employee.primary_mobile.value == "+92 300 5550001"
        assert employee.primary_email.value == "multi@example.com"
        assert [c.is_primary for c in employee.emergency_contacts.all()] == [True, False]

    def test_creation_writes_audit_and_timeline_entries(self, hr_admin, employee):
        assert AuditLog.objects.filter(
            object_type="employee", object_id=str(employee.pk), action__icontains="employee_created"
        ).exists()
        assert TimelineEntry.objects.filter(
            employee=employee, event_type="employee_created"
        ).exists()


class TestEmployeePermissions:
    def test_anonymous_actor_is_rejected(self, db, make_employee, normal_user):
        with pytest.raises(PermissionDeniedException):
            make_employee(actor=normal_user)

    def test_officer_may_create_but_not_archive(self, hr_officer):
        employee = EmployeeService.create_employee(
            actor=hr_officer,
            person_data={"first_name": "Officer", "last_name": "Created"},
            contacts=[{"contact_type": "mobile", "value": "+92 300 1234567"}],
        )
        with pytest.raises(PermissionDeniedException):
            EmployeeService.change_status(
                employee, actor=hr_officer, status=EmployeeStatus.ARCHIVED, reason="left"
            )

    def test_employee_is_not_deletable(self, employee):
        """ADR-022: the reason is enforced in one place and explains itself."""
        with pytest.raises(BusinessRuleException) as exc:
            EmployeeService.assert_can_delete(employee, actor=None)
        assert exc.value.code == "employee_deletion_not_allowed"
        assert not hasattr(EmployeeService, "delete_employee")

    def test_person_fk_is_protected(self, employee):
        with pytest.raises(IntegrityError), transaction.atomic():
            Person.objects.filter(pk=employee.person_id).delete()


class TestEmployeeStatus:
    @pytest.mark.parametrize(
        ("start", "target"),
        [
            (EmployeeStatus.ACTIVE, EmployeeStatus.INACTIVE),
            (EmployeeStatus.ACTIVE, EmployeeStatus.ARCHIVED),
            (EmployeeStatus.INACTIVE, EmployeeStatus.ACTIVE),
            (EmployeeStatus.INACTIVE, EmployeeStatus.ARCHIVED),
        ],
    )
    def test_legal_transitions(self, hr_admin, make_employee, start, target):
        employee = make_employee(actor=hr_admin, status=start)
        assert EmployeeService.change_status(employee, actor=hr_admin, status=target)
        employee.refresh_from_db()
        assert employee.employee_status == target

    def test_archived_is_terminal_until_an_explicit_restore(self, hr_admin, make_employee):
        employee = make_employee(actor=hr_admin)
        EmployeeService.change_status(employee, actor=hr_admin, status=EmployeeStatus.ARCHIVED)
        employee.refresh_from_db()

        with pytest.raises(BusinessRuleException) as exc:
            EmployeeService.change_status(employee, actor=hr_admin, status=EmployeeStatus.ACTIVE)
        assert exc.value.code == "invalid_status_transition"

        # reactivate() is the documented, audited way back - used by Phase 4 separation reversal.
        EmployeeService.reactivate(employee, actor=hr_admin, reason="record restored")
        employee.refresh_from_db()
        assert employee.employee_status == EmployeeStatus.ACTIVE
        assert employee.archived_at is None

    def test_archiving_stamps_the_timestamp_and_clears_it_on_restore(self, hr_admin, make_employee):
        employee = make_employee(actor=hr_admin)
        EmployeeService.archive(employee, actor=hr_admin, reason="departed")
        employee.refresh_from_db()
        assert employee.archived_at is not None

        EmployeeService.reactivate(employee, actor=hr_admin)
        employee.refresh_from_db()
        assert employee.archived_at is None

    def test_setting_the_same_status_is_a_no_op(self, hr_admin, employee):
        assert EmployeeService.change_status(employee, actor=hr_admin, status=EmployeeStatus.ACTIVE)
        assert not AuditLog.objects.filter(
            object_id=str(employee.pk), action__icontains="status_changed"
        ).exists()

    def test_rejects_an_unknown_status(self, hr_admin, employee):
        with pytest.raises(ValidationException):
            EmployeeService.change_status(employee, actor=hr_admin, status="transferred")

    def test_rejects_statuses_owned_by_later_phases(self, hr_admin, employee):
        """The lifecycle belongs to Employment/Lifecycle modules, not to ``Employee``."""
        for phase4_status in ("on_leave", "terminated", "transferred", "joined"):
            with pytest.raises(ValidationException):
                EmployeeService.change_status(employee, actor=hr_admin, status=phase4_status)

    def test_status_change_is_audited_with_a_reason(self, hr_admin, employee):
        EmployeeService.change_status(
            employee, actor=hr_admin, status=EmployeeStatus.INACTIVE, reason="long leave"
        )
        row = AuditLog.objects.filter(
            object_id=str(employee.pk), action__icontains="employee_status_changed"
        ).get()
        assert row.changes["before"]["employee_status"] == EmployeeStatus.ACTIVE
        assert row.changes["after"]["employee_status"] == EmployeeStatus.INACTIVE
        assert row.reason == "long leave"


class TestEmployeeUserLink:
    def test_link_and_unlink_are_audited(self, hr_admin, employee, make_user):
        user = make_user("linked@example.com")

        EmployeeService.link_user(employee, actor=hr_admin, user=user)
        employee.refresh_from_db()
        assert employee.user_id == user.pk
        assert AuditLog.objects.filter(
            object_id=str(employee.pk), action__icontains="user_linked"
        ).exists()

        EmployeeService.unlink_user(employee, actor=hr_admin, reason="wrong account")
        employee.refresh_from_db()
        assert employee.user_id is None
        assert AuditLog.objects.filter(
            object_id=str(employee.pk), action__icontains="user_unlinked"
        ).exists()

    def test_unlinking_leaves_the_user_account_alone(self, hr_admin, employee, make_user):
        """ADR-002: unlinking must never delete or disable a login."""
        user = make_user("keep@example.com")
        EmployeeService.link_user(employee, actor=hr_admin, user=user)
        EmployeeService.unlink_user(employee, actor=hr_admin)

        user.refresh_from_db()
        assert user.pk is not None
        assert user.status == "active"
        assert not Employee.objects.filter(user=user).exists()

    def test_an_account_can_only_belong_to_one_employee(
        self, hr_admin, employee, make_employee, make_user
    ):
        user = make_user("shared@example.com")
        EmployeeService.link_user(employee, actor=hr_admin, user=user)

        other = make_employee(actor=hr_admin)
        with pytest.raises(ConflictException) as exc:
            EmployeeService.link_user(other, actor=hr_admin, user=user)
        assert exc.value.code == "user_already_linked"

    def test_creating_an_employee_can_link_a_user_in_one_transaction(self, hr_admin, make_user):
        user = make_user("joined@example.com")
        employee = EmployeeService.create_employee(
            actor=hr_admin,
            person_data={
                "first_name": "New",
                "last_name": "Starter",
                "date_of_birth": "2000-02-02",
            },
            link_user=user,
        )
        assert employee.user_id == user.pk

    def test_relinking_after_unlink_is_allowed(self, hr_admin, employee, make_user):
        user = make_user("again@example.com")
        EmployeeService.link_user(employee, actor=hr_admin, user=user)
        EmployeeService.unlink_user(employee, actor=hr_admin)
        EmployeeService.link_user(employee, actor=hr_admin, user=user)
        employee.refresh_from_db()
        assert employee.user_id == user.pk


class TestEmployeeUpdate:
    def test_updating_personal_details_through_the_employee(self, hr_admin, employee):
        EmployeeService.update_employee(
            employee, actor=hr_admin, person_data={"last_name": "Renamed"}
        )
        employee.refresh_from_db()
        assert employee.person.last_name == "Renamed"

    def test_update_ignores_unknown_fields(self, hr_admin, employee):
        EmployeeService.update_employee(
            employee, actor=hr_admin, data={"employee_status": "active"}
        )
        employee.refresh_from_db()
        assert employee.employee_status == EmployeeStatus.ACTIVE

    def test_outbox_event_is_emitted_for_person_details(self, hr_admin, employee):
        EmployeeService.update_employee(employee, actor=hr_admin, person_data={"middle_name": "B"})
        assert OutboxEvent.objects.filter(event_type__icontains="employee").exists()


class TestPersonIsolation:
    """A ``Person`` may exist with no ``Employee`` - recruitment creates people before roles."""

    def test_a_person_can_exist_without_an_employee(self, hr_admin):
        person = PersonService.create_person(
            actor=hr_admin, data={"first_name": "Candidate", "last_name": "Only"}
        )
        assert Person.objects.filter(pk=person.pk).exists()
        with pytest.raises(Employee.DoesNotExist):  # reverse one-to-one: no employee record
            _ = person.employee

    def test_one_employee_per_person(self, employee):
        with pytest.raises(IntegrityError), transaction.atomic():
            Employee.objects.create(person=employee.person, code="EMP-999999")


class TestDomainEvents:
    def test_creation_publishes_an_outbox_event(self, hr_admin, make_employee):
        employee = make_employee(actor=hr_admin)
        assert OutboxEvent.objects.filter(aggregate_id=str(employee.pk)).exists()

    def test_status_change_and_user_link_publish_events(self, hr_admin, employee, make_user):
        EmployeeService.change_status(employee, actor=hr_admin, status=EmployeeStatus.INACTIVE)
        EmployeeService.link_user(employee, actor=hr_admin, user=make_user("ev@example.com"))

        types = set(OutboxEvent.objects.values_list("event_type", flat=True))
        assert any("status" in t for t in types)
        assert any("user" in t and "link" in t for t in types)


class TestAgeRules:
    def test_rejects_an_implausible_date_of_birth(self, hr_admin):
        with pytest.raises(ValidationException) as exc:
            EmployeeService.create_employee(
                actor=hr_admin,
                person_data={
                    "first_name": "Ancient",
                    "last_name": "Person",
                    "date_of_birth": "1890-01-01",
                },
            )
        assert "date_of_birth" in exc.value.details

    def test_rejects_a_future_date_of_birth(self, hr_admin):
        future = dt.date.today() + dt.timedelta(days=30)
        with pytest.raises(ValidationException) as exc:
            EmployeeService.create_employee(
                actor=hr_admin,
                person_data={"first_name": "Future", "last_name": "Baby", "date_of_birth": future},
            )
        assert "date_of_birth" in exc.value.details

    def test_accepts_a_child_below_the_adult_age(self, hr_admin):
        """Phase 3 has no employment rules; a minor can be a person, employment comes later."""
        child = EmployeeService.create_employee(
            actor=hr_admin,
            person_data={
                "first_name": "Young",
                "last_name": "Person",
                "date_of_birth": dt.date.today().replace(year=dt.date.today().year - 12),
            },
        )
        assert child.person.age == 12

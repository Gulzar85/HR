"""Django admin = read-only fallback for employee data.

Every change goes through the employee UI/API (services enforce permissions, scope, audit and
sensitive-data rules). Identifier values are shown masked even here; nothing can be deleted.
"""

from django.contrib import admin

from .models import (
    Address,
    Contact,
    EmergencyContact,
    Employee,
    EmployeeIdentifier,
    EmployeeNote,
    Person,
    PersonRelationship,
    TimelineEntry,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Person)
class PersonAdmin(ReadOnlyAdmin):
    list_display = ("last_name", "first_name", "preferred_name", "created_at")
    search_fields = ("first_name", "last_name", "preferred_name")
    exclude = ("date_of_birth", "gender", "nationality", "profile_photo")


@admin.register(Employee)
class EmployeeAdmin(ReadOnlyAdmin):
    list_display = ("code", "person", "employee_status", "user", "created_at")
    list_filter = ("employee_status",)
    search_fields = ("code", "person__first_name", "person__last_name")
    list_select_related = ("person", "user")


@admin.register(EmployeeIdentifier)
class EmployeeIdentifierAdmin(ReadOnlyAdmin):
    list_display = (
        "employee",
        "identifier_type",
        "masked_value",
        "verification_status",
        "is_primary",
    )
    list_filter = ("identifier_type", "verification_status")
    search_fields = ("employee__code",)
    exclude = ("value", "normalized_value")
    list_select_related = ("employee__person",)


@admin.register(Contact)
class ContactAdmin(ReadOnlyAdmin):
    list_display = ("employee", "contact_type", "value", "is_primary")
    list_filter = ("contact_type", "is_primary")
    search_fields = ("employee__code", "normalized_value")
    list_select_related = ("employee__person",)


@admin.register(Address)
class AddressAdmin(ReadOnlyAdmin):
    list_display = (
        "employee",
        "address_type",
        "city",
        "is_primary",
        "effective_from",
        "effective_to",
    )
    list_filter = ("address_type", "is_primary")
    search_fields = ("employee__code", "city")
    list_select_related = ("employee__person",)


@admin.register(EmergencyContact)
class EmergencyContactAdmin(ReadOnlyAdmin):
    list_display = ("employee", "name", "relationship", "is_primary")
    list_filter = ("relationship",)
    search_fields = ("employee__code", "name")
    list_select_related = ("employee__person",)


@admin.register(PersonRelationship)
class PersonRelationshipAdmin(ReadOnlyAdmin):
    list_display = ("from_person", "relationship_type", "to_person")


@admin.register(EmployeeNote)
class EmployeeNoteAdmin(ReadOnlyAdmin):
    list_display = ("employee", "visibility", "created_by", "created_at")
    exclude = ("content",)


@admin.register(TimelineEntry)
class TimelineEntryAdmin(ReadOnlyAdmin):
    list_display = ("occurred_at", "employee", "event_type", "summary", "source_app")
    list_filter = ("event_type", "source_app")
    search_fields = ("employee__code",)

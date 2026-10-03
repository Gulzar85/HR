"""Django admin = read-only fallback for organization data.

All changes go through the organization UI/API (services enforce hierarchy, scope, history). The
admin never adds, edits or deletes organization records.
"""

from django.contrib import admin

from .models import (
    Area,
    Company,
    CorporateLocation,
    Department,
    Division,
    OrganizationHistory,
    OrganizationRelationship,
    Region,
    Restaurant,
)


class ReadOnlyOrgAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "effective_from", "effective_to")
    list_filter = ("status",)
    search_fields = ("code", "name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for _model in (Company, Division, CorporateLocation, Department, Region, Area, Restaurant):
    admin.site.register(_model, ReadOnlyOrgAdmin)


@admin.register(OrganizationHistory)
class OrganizationHistoryAdmin(ReadOnlyOrgAdmin):
    list_display = ("timestamp", "entity_type", "entity_code", "event", "actor")  # type: ignore[assignment]
    list_filter = ("entity_type", "event")  # type: ignore[assignment]
    search_fields = ("entity_code",)  # type: ignore[assignment]


@admin.register(OrganizationRelationship)
class OrganizationRelationshipAdmin(ReadOnlyOrgAdmin):
    list_display = (  # type: ignore[assignment]
        "child_type",
        "child_id",
        "parent_type",
        "parent_id",
        "effective_from",
        "effective_to",
    )
    list_filter = ("child_type",)
    search_fields = ()  # type: ignore[assignment]

"""Employee web URLs (mounted at /employees/)."""

from django.urls import path

from .views.contacts import views as c
from .views.employees import views as e

app_name = "employees"

urlpatterns = [
    path("", e.EmployeeListView.as_view(), name="list"),
    path("new/", e.EmployeeCreateView.as_view(), name="create"),
    path("export/", e.EmployeeExportView.as_view(), name="export"),
    path("<uuid:pk>/", e.EmployeeDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", e.EmployeeEditView.as_view(), name="edit"),
    path("<uuid:pk>/status/", e.EmployeeStatusView.as_view(), name="status"),
    path("<uuid:pk>/account/link/", e.EmployeeLinkUserView.as_view(), name="link_user"),
    path("<uuid:pk>/account/unlink/", e.EmployeeUnlinkUserView.as_view(), name="unlink_user"),
    path("<uuid:pk>/photo/", e.EmployeePhotoView.as_view(), name="photo"),
    path("<uuid:pk>/timeline/", e.EmployeeTimelineView.as_view(), name="timeline"),
    path(
        "<uuid:pk>/identifiers/reveal/", e.IdentifierRevealView.as_view(), name="identifiers_reveal"
    ),
    # inline section editors
    path("<uuid:pk>/contacts/add/", c.ContactAddView.as_view(), name="contact_add"),
    path(
        "<uuid:pk>/contacts/<uuid:item>/primary/",
        c.ContactPrimaryView.as_view(),
        name="contact_primary",
    ),
    path(
        "<uuid:pk>/contacts/<uuid:item>/remove/",
        c.ContactRemoveView.as_view(),
        name="contact_remove",
    ),
    path("<uuid:pk>/addresses/add/", c.AddressAddView.as_view(), name="address_add"),
    path(
        "<uuid:pk>/addresses/<uuid:item>/close/", c.AddressCloseView.as_view(), name="address_close"
    ),
    path("<uuid:pk>/emergency-contacts/add/", c.EmergencyAddView.as_view(), name="emergency_add"),
    path(
        "<uuid:pk>/emergency-contacts/<uuid:item>/primary/",
        c.EmergencyPrimaryView.as_view(),
        name="emergency_primary",
    ),
    path(
        "<uuid:pk>/emergency-contacts/<uuid:item>/remove/",
        c.EmergencyRemoveView.as_view(),
        name="emergency_remove",
    ),
    path("<uuid:pk>/identifiers/add/", c.IdentifierAddView.as_view(), name="identifier_add"),
    path(
        "<uuid:pk>/identifiers/<uuid:item>/verify/",
        c.IdentifierVerifyView.as_view(),
        name="identifier_verify",
    ),
    path(
        "<uuid:pk>/identifiers/<uuid:item>/remove/",
        c.IdentifierRemoveView.as_view(),
        name="identifier_remove",
    ),
    path("<uuid:pk>/notes/add/", c.NoteAddView.as_view(), name="note_add"),
    path("<uuid:pk>/notes/<uuid:item>/remove/", c.NoteRemoveView.as_view(), name="note_remove"),
]

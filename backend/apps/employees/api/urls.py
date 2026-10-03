"""Mounted by apps/api/v1/urls.py at /api/v1/employees/."""

from django.urls import path

from .. import permissions as P
from . import views as v

employee_urlpatterns = [
    path("", v.EmployeeListCreateAPI.as_view(), name="employee-list"),
    path("<uuid:pk>/", v.EmployeeDetailAPI.as_view(), name="employee-detail"),
    path("<uuid:pk>/status/", v.EmployeeStatusAPI.as_view(), name="employee-status"),
    path("<uuid:pk>/user-link/", v.EmployeeUserLinkAPI.as_view(), name="employee-user-link"),
    path("<uuid:pk>/contacts/", v.ContactsAPI.as_view(), name="employee-contacts"),
    path(
        "<uuid:pk>/contacts/<uuid:item>/",
        v.delete_view("contacts", P.MANAGE_CONTACTS).as_view(),
        name="employee-contact",
    ),
    path("<uuid:pk>/addresses/", v.AddressesAPI.as_view(), name="employee-addresses"),
    path(
        "<uuid:pk>/addresses/<uuid:item>/",
        v.delete_view("addresses", P.MANAGE_ADDRESSES).as_view(),
        name="employee-address",
    ),
    path(
        "<uuid:pk>/emergency-contacts/",
        v.EmergencyContactsAPI.as_view(),
        name="employee-emergency-contacts",
    ),
    path(
        "<uuid:pk>/emergency-contacts/<uuid:item>/",
        v.delete_view("emergency_contacts", P.MANAGE_EMERGENCY_CONTACTS).as_view(),
        name="employee-emergency-contact",
    ),
    path("<uuid:pk>/identifiers/", v.IdentifiersAPI.as_view(), name="employee-identifiers"),
    path(
        "<uuid:pk>/identifiers/<uuid:item>/",
        v.delete_view("identifiers", P.MANAGE_IDENTIFIERS).as_view(),
        name="employee-identifier",
    ),
    path(
        "<uuid:pk>/identifiers/<uuid:item>/verification/",
        v.IdentifierVerifyAPI.as_view(),
        name="employee-identifier-verify",
    ),
    path("<uuid:pk>/timeline/", v.TimelineAPI.as_view(), name="employee-timeline"),
]

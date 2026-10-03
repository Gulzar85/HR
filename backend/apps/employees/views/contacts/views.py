"""Inline (HTMX) editors for contacts, addresses, emergency contacts, identifiers and notes.

Every child record is looked up **through the scoped employee** (``employee.<relation>``), so an id
belonging to another employee is a 404 even for an otherwise authorized user. The services re-check
permission and scope on every write.
"""

from __future__ import annotations

from django.http import Http404

from ... import permissions as P
from ...forms import (
    AddressForm,
    ContactForm,
    EmergencyContactForm,
    IdentifierForm,
    NoteForm,
    VerificationForm,
)
from ...services import (
    AddressService,
    ContactService,
    EmergencyContactService,
    IdentifierService,
    NoteService,
)
from ..base import SectionActionView, capabilities


def _child(qs, pk):
    obj = qs.filter(pk=pk).first()
    if obj is None:
        raise Http404("Not found.")
    return obj


# ----------------------------------------------------------------------------- contacts
class ContactAddView(SectionActionView):
    section = "contacts"
    permission_required = P.MANAGE_CONTACTS
    form_class = ContactForm
    title = "Add contact"
    success_message = "Contact added."

    def perform(self, form):
        ContactService.add_contact(
            employee=self.employee, actor=self.request.user, data=form.cleaned_data, ctx=self.ctx
        )


class ContactPrimaryView(SectionActionView):
    section = "contacts"
    permission_required = P.MANAGE_CONTACTS
    http_method_names = ["post"]
    success_message = "Primary contact updated."

    def perform(self, form):
        contact = _child(self.employee.contacts, self.kwargs["item"])
        ContactService.set_primary(contact, actor=self.request.user, ctx=self.ctx)


class ContactRemoveView(SectionActionView):
    section = "contacts"
    permission_required = P.MANAGE_CONTACTS
    http_method_names = ["post"]
    success_message = "Contact removed."

    def perform(self, form):
        contact = _child(self.employee.contacts, self.kwargs["item"])
        ContactService.remove_contact(contact, actor=self.request.user, ctx=self.ctx)


# ---------------------------------------------------------------------------- addresses
class AddressAddView(SectionActionView):
    section = "addresses"
    permission_required = (P.VIEW_SENSITIVE_CONTACTS, P.MANAGE_ADDRESSES)
    form_class = AddressForm
    title = "Record address"
    success_message = "Address recorded. Any previous address of that type was closed, not deleted."

    def perform(self, form):
        data = {k: v for k, v in form.cleaned_data.items() if v not in (None, "")}
        AddressService.add_address(
            employee=self.employee, actor=self.request.user, data=data, ctx=self.ctx
        )


class AddressCloseView(SectionActionView):
    section = "addresses"
    permission_required = (P.VIEW_SENSITIVE_CONTACTS, P.MANAGE_ADDRESSES)
    http_method_names = ["post"]
    success_message = "Address closed. It stays in the address history."

    def perform(self, form):
        address = _child(self.employee.addresses, self.kwargs["item"])
        AddressService.close_address(address, actor=self.request.user, ctx=self.ctx)


# ------------------------------------------------------------------- emergency contacts
class EmergencyAddView(SectionActionView):
    section = "emergency"
    permission_required = (P.VIEW_EMERGENCY_CONTACTS, P.MANAGE_EMERGENCY_CONTACTS)
    form_class = EmergencyContactForm
    title = "Add emergency contact"
    success_message = "Emergency contact added."

    def perform(self, form):
        data = {k: v for k, v in form.cleaned_data.items() if v not in (None, "")}
        EmergencyContactService.add_emergency_contact(
            employee=self.employee, actor=self.request.user, data=data, ctx=self.ctx
        )


class EmergencyPrimaryView(SectionActionView):
    section = "emergency"
    permission_required = (P.VIEW_EMERGENCY_CONTACTS, P.MANAGE_EMERGENCY_CONTACTS)
    http_method_names = ["post"]
    success_message = "Primary emergency contact updated."

    def perform(self, form):
        contact = _child(self.employee.emergency_contacts, self.kwargs["item"])
        EmergencyContactService.update_emergency_contact(
            contact, actor=self.request.user, data={"is_primary": True}, ctx=self.ctx
        )


class EmergencyRemoveView(SectionActionView):
    section = "emergency"
    permission_required = (P.VIEW_EMERGENCY_CONTACTS, P.MANAGE_EMERGENCY_CONTACTS)
    http_method_names = ["post"]
    success_message = "Emergency contact removed."

    def perform(self, form):
        contact = _child(self.employee.emergency_contacts, self.kwargs["item"])
        EmergencyContactService.remove_emergency_contact(
            contact, actor=self.request.user, ctx=self.ctx
        )


# --------------------------------------------------------------------------- identifiers
class IdentifierAddView(SectionActionView):
    section = "identifiers"
    permission_required = (P.VIEW_IDENTIFIERS, P.MANAGE_IDENTIFIERS)
    form_class = IdentifierForm
    title = "Add identifier"
    success_message = "Identifier added."

    def perform(self, form):
        data = {k: v for k, v in form.cleaned_data.items() if v not in (None, "")}
        IdentifierService.add_identifier(
            employee=self.employee, actor=self.request.user, data=data, ctx=self.ctx
        )


class IdentifierVerifyView(SectionActionView):
    section = "identifiers"
    permission_required = (P.VIEW_IDENTIFIERS, P.MANAGE_IDENTIFIERS)
    form_class = VerificationForm
    http_method_names = ["post"]
    success_message = "Verification status updated."

    def perform(self, form):
        identifier = _child(self.employee.identifiers, self.kwargs["item"])
        IdentifierService.set_verification(
            identifier,
            actor=self.request.user,
            status=form.cleaned_data["verification_status"],
            ctx=self.ctx,
        )


class IdentifierRemoveView(SectionActionView):
    section = "identifiers"
    permission_required = (P.VIEW_IDENTIFIERS, P.MANAGE_IDENTIFIERS)
    http_method_names = ["post"]
    success_message = "Identifier removed."

    def perform(self, form):
        identifier = _child(self.employee.identifiers, self.kwargs["item"])
        IdentifierService.remove_identifier(identifier, actor=self.request.user, ctx=self.ctx)


# --------------------------------------------------------------------------------- notes
class NoteAddView(SectionActionView):
    section = "notes"
    permission_required = P.MANAGE_NOTES
    form_class = NoteForm
    title = "Add note"
    success_message = "Note added."

    def get_form_kwargs(self):
        return {"allow_restricted": capabilities(self.request.user)["view_sensitive"]}

    def perform(self, form):
        NoteService.add_note(
            employee=self.employee, actor=self.request.user, data=form.cleaned_data, ctx=self.ctx
        )


class NoteRemoveView(SectionActionView):
    section = "notes"
    permission_required = P.MANAGE_NOTES
    http_method_names = ["post"]
    success_message = "Note removed."

    def perform(self, form):
        note = _child(self.employee.notes, self.kwargs["item"])
        NoteService.remove_note(note, actor=self.request.user, ctx=self.ctx)

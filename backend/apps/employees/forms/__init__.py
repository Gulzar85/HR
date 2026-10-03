"""Employee-domain forms. Forms collect input; services decide (permissions, scope, rules).

Field names match the service ``EDITABLE_FIELDS`` so ``form.cleaned_data`` is passed straight to the
service. Sensitive inputs (date of birth, gender, nationality, identifiers) are only *included* in a
form when the user may edit them - and the services re-check regardless.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from ..models import (
    AddressType,
    ContactType,
    EmployeeStatus,
    IdentifierType,
    NoteVisibility,
    RelationshipType,
    VerificationStatus,
    country_choices,
    gender_choices,
)

DATE = forms.DateInput(attrs={"type": "date"})


def _country_field(label: str, required: bool = False) -> forms.ChoiceField:
    return forms.ChoiceField(
        label=label, required=required, choices=[("", "—"), *country_choices()]
    )


class PersonForm(forms.Form):
    """Personal identity. ``sensitive=False`` drops DOB/gender/nationality entirely."""

    first_name = forms.CharField(label=_("First name"), max_length=80)
    middle_name = forms.CharField(label=_("Middle name"), max_length=80, required=False)
    last_name = forms.CharField(label=_("Last name"), max_length=80)
    preferred_name = forms.CharField(
        label=_("Preferred name"), max_length=80, required=False,
        help_text=_("Optional. Shown instead of the full name."),
    )  # fmt: skip
    date_of_birth = forms.DateField(label=_("Date of birth"), required=False, widget=DATE)
    gender = forms.ChoiceField(label=_("Gender"), required=False, choices=gender_choices())
    nationality = forms.ChoiceField(label=_("Nationality"), required=False)

    SENSITIVE = ("date_of_birth", "gender", "nationality")

    def __init__(self, *args: Any, sensitive: bool = True, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["nationality"].choices = [("", "Not declared"), *country_choices()]
        if not sensitive:
            for name in self.SENSITIVE:
                del self.fields[name]


class PhotoForm(forms.Form):
    profile_photo = forms.FileField(
        label=_("Profile photo"), required=False,
        help_text=_("JPEG, PNG, GIF or WEBP. The file content is checked, not just the name."),
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/gif,image/webp"}),
    )  # fmt: skip
    remove_photo = forms.BooleanField(label=_("Remove current photo"), required=False)


class InitialContactsForm(forms.Form):
    """Create-page shortcut: the usual primary channels. All optional."""

    mobile = forms.CharField(label=_("Mobile"), max_length=40, required=False)
    email = forms.EmailField(label=_("Email"), required=False)
    phone = forms.CharField(label=_("Phone (landline)"), max_length=40, required=False)

    def contacts(self) -> list[dict[str, Any]]:
        d = self.cleaned_data
        mapping = [
            (ContactType.MOBILE, "mobile"),
            (ContactType.EMAIL, "email"),
            (ContactType.PHONE, "phone"),
        ]
        return [{"contact_type": t, "value": d[f]} for t, f in mapping if d.get(f)]


class ContactForm(forms.Form):
    contact_type = forms.ChoiceField(label=_("Type"), choices=ContactType.choices)
    value = forms.CharField(label=_("Value"), max_length=160)
    label = forms.CharField(label=_("Label"), max_length=60, required=False)
    is_primary = forms.BooleanField(label=_("Primary for this type"), required=False)


class AddressForm(forms.Form):
    address_type = forms.ChoiceField(label=_("Type"), choices=AddressType.choices)
    address_line_1 = forms.CharField(label=_("Address line 1"), max_length=200)
    address_line_2 = forms.CharField(label=_("Address line 2"), max_length=200, required=False)
    city = forms.CharField(label=_("City"), max_length=100)
    state_province = forms.CharField(label=_("State / province"), max_length=100, required=False)
    postal_code = forms.CharField(label=_("Postal code"), max_length=20, required=False)
    country = forms.ChoiceField(label=_("Country"), required=False)
    effective_from = forms.DateField(
        label=_("Effective from"), required=False, widget=DATE,
        help_text=_("Defaults to today. A previous address of the same type is closed, not deleted."),
    )  # fmt: skip

    def __init__(self, *args: Any, optional: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["country"].choices = [("", "—"), *country_choices()]
        self.optional = optional
        if optional:  # create page: the whole block may be left empty
            for f in self.fields.values():
                f.required = False

    def is_blank(self) -> bool:
        return not any(self.cleaned_data.get(f) for f in ("address_line_1", "city"))

    def clean(self):
        data = super().clean()
        if self.optional and not self.is_blank():
            for f in ("address_line_1", "city"):
                if not data.get(f):
                    self.add_error(f, _("Required when an address is entered."))
        return data


class EmergencyContactForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=150)
    relationship = forms.ChoiceField(label=_("Relationship"), choices=RelationshipType.choices)
    phone = forms.CharField(label=_("Phone"), max_length=40)
    alternative_phone = forms.CharField(label=_("Alternative phone"), max_length=40, required=False)
    email = forms.EmailField(label=_("Email"), required=False)
    address = forms.CharField(
        label=_("Address"), required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    is_primary = forms.BooleanField(label=_("Primary emergency contact"), required=False)

    def __init__(self, *args: Any, optional: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.optional = optional
        if optional:
            for f in self.fields.values():
                f.required = False
            self.fields["relationship"].choices = [("", "—"), *RelationshipType.choices]

    def is_blank(self) -> bool:
        return not any(self.cleaned_data.get(f) for f in ("name", "phone"))

    def clean(self):
        data = super().clean()
        if self.optional and not self.is_blank():
            for f in ("name", "relationship", "phone"):
                if not data.get(f):
                    self.add_error(f, _("Required when an emergency contact is entered."))
        return data


class IdentifierForm(forms.Form):
    identifier_type = forms.ChoiceField(label=_("Type"), choices=IdentifierType.choices)
    value = forms.CharField(
        label=_("Number"), max_length=64, widget=forms.TextInput(attrs={"autocomplete": "off"})
    )
    issuing_country = forms.ChoiceField(label=_("Issuing country"), required=False)
    issue_date = forms.DateField(label=_("Issue date"), required=False, widget=DATE)
    expiry_date = forms.DateField(label=_("Expiry date"), required=False, widget=DATE)

    def __init__(self, *args: Any, optional: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["issuing_country"].choices = [("", "—"), *country_choices()]
        self.optional = optional
        if optional:
            self.fields["value"].required = False
            self.fields["identifier_type"].required = False
            self.fields["identifier_type"].choices = [("", "—"), *IdentifierType.choices]

    def is_blank(self) -> bool:
        return not self.cleaned_data.get("value")

    def clean(self):
        data = super().clean()
        if self.optional and data.get("value") and not data.get("identifier_type"):
            self.add_error("identifier_type", _("Choose the identifier type."))
        return data


class VerificationForm(forms.Form):
    verification_status = forms.ChoiceField(
        label=_("Verification"), choices=VerificationStatus.choices
    )


class NoteForm(forms.Form):
    content = forms.CharField(label=_("Note"), widget=forms.Textarea(attrs={"rows": 3}))
    visibility = forms.ChoiceField(label=_("Visibility"), choices=NoteVisibility.choices)
    pinned = forms.BooleanField(label=_("Pin to top"), required=False)

    def __init__(self, *args: Any, allow_restricted: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not allow_restricted:
            self.fields["visibility"].choices = [
                (NoteVisibility.INTERNAL, NoteVisibility.INTERNAL.label)
            ]


class StatusForm(forms.Form):
    employee_status = forms.ChoiceField(label=_("New status"))
    reason = forms.CharField(
        label=_("Reason"), max_length=255, widget=forms.Textarea(attrs={"rows": 2})
    )

    def __init__(self, *args: Any, choices: list[str], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["employee_status"].choices = [(c, EmployeeStatus(c).label) for c in choices]


class LinkUserForm(forms.Form):
    email = forms.EmailField(
        label=_("User account email"),
        help_text=_("The existing login account to link. No account is created."),
    )


class DuplicateConfirmForm(forms.Form):
    confirm_duplicates = forms.BooleanField(
        label=_("I have checked the possible duplicates and still want to create this employee"),
        required=False,
    )

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from ..models import Role


class RoleForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=100)
    code = forms.SlugField(
        label=_("Code"),
        max_length=60,
        help_text=_("Stable machine name, e.g. hr-administrator. Cannot change later."),
    )
    description = forms.CharField(label=_("Description"), max_length=500, required=False)

    def __init__(self, *args, instance: Role | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance is not None:
            self.fields["code"].disabled = True  # immutable


class PermissionSelectionForm(forms.Form):
    """Checkbox matrix posted as repeated ``permissions`` ids; validated against assignable perms."""

    permissions = forms.TypedMultipleChoiceField(required=False, coerce=int, choices=())

    def __init__(self, *args, assignable_ids: list[int], **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].choices = [(i, str(i)) for i in assignable_ids]


class GroupForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=150)
    description = forms.CharField(label=_("Description"), max_length=500, required=False)


class AddMemberForm(forms.Form):
    email = forms.EmailField(label=_("User email"), max_length=254)

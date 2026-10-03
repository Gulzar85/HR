from __future__ import annotations

from django import forms
from django.contrib.auth.models import Group
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from ..models import Role
from ..services.scope_service import registered_scope_types

USERNAME_VALIDATOR = RegexValidator(r"^[\w.@+-]+$", _("Letters, digits and @/./+/-/_ only."))

STATUS_ACTIONS = [
    ("activate", _("Activate")),
    ("deactivate", _("Deactivate")),
    ("suspend", _("Suspend")),
    ("unlock", _("Unlock")),
]


class UserCreateForm(forms.Form):
    email = forms.EmailField(label=_("Email"), max_length=254)
    first_name = forms.CharField(label=_("First name"), max_length=150)
    last_name = forms.CharField(label=_("Last name"), max_length=150)
    username = forms.CharField(
        label=_("Username"),
        max_length=150,
        required=False,
        validators=[USERNAME_VALIDATOR],
        help_text=_(
            "Optional handle. Generated from the email if left blank. Not used to sign in."
        ),
    )
    initial_password = forms.CharField(
        label=_("Initial password"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_("Leave blank to e-mail an activation link instead (recommended)."),
    )
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Roles"),
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Groups"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["roles"].queryset = Role.objects.filter(is_active=True).order_by("name")
        self.fields["groups"].queryset = Group.objects.filter(profile__is_active=True).order_by(
            "name"
        )


class UserEditForm(forms.Form):
    email = forms.EmailField(label=_("Email"), max_length=254)
    first_name = forms.CharField(label=_("First name"), max_length=150)
    last_name = forms.CharField(label=_("Last name"), max_length=150)
    username = forms.CharField(label=_("Username"), max_length=150, validators=[USERNAME_VALIDATOR])


class StatusActionForm(forms.Form):
    action = forms.ChoiceField(choices=STATUS_ACTIONS)
    reason = forms.CharField(label=_("Reason"), max_length=255, required=False)


class AdminSetPasswordForm(forms.Form):
    password = forms.CharField(
        label=_("New password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirm_password = forms.CharField(
        label=_("Confirm password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        data = super().clean()
        if data.get("password") != data.get("confirm_password"):
            self.add_error("confirm_password", _("The two passwords do not match."))
        return data


class UserRolesForm(forms.Form):
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Roles"),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # active roles, plus any inactive role the user already holds (so it can be removed)
        held = user.roles.values_list("pk", flat=True) if user else []
        self.fields["roles"].queryset = (
            (Role.objects.filter(is_active=True) | Role.objects.filter(pk__in=list(held)))
            .distinct()
            .order_by("name")
        )


class UserGroupsForm(forms.Form):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Groups"),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        held = user.groups.values_list("pk", flat=True) if user else []
        self.fields["groups"].queryset = (
            (
                Group.objects.filter(profile__is_active=True)
                | Group.objects.filter(pk__in=list(held))
            )
            .distinct()
            .order_by("name")
        )


class ScopeGrantForm(forms.Form):
    scope_type = forms.ChoiceField(label=_("Scope type"))
    scope_ref = forms.CharField(
        label=_("Reference"),
        max_length=64,
        required=False,
        help_text=_("Id or code of the organization unit (not needed for 'Entire organization')."),
    )
    include_descendants = forms.BooleanField(
        label=_("Include units below"), required=False, initial=True
    )
    expires_at = forms.DateTimeField(
        label=_("Expires"),
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["scope_type"].choices = [
            (t.name, t.label) for t in registered_scope_types().values()
        ]

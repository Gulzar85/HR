from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.utils.translation import gettext_lazy as _


class LoginForm(AuthenticationForm):
    """Email + password. The field keeps Django's name ``username`` (USERNAME_FIELD is email)."""

    username = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(
            attrs={"autofocus": True, "autocomplete": "email", "inputmode": "email"}
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    remember_me = forms.BooleanField(required=False, label=_("Keep me signed in on this device"))

    error_messages = {
        # One generic message for every failure: unknown email, wrong password, locked,
        # suspended, inactive. Never reveals whether an account exists or why access failed.
        "invalid_login": _("The email or password is incorrect, or the account is unavailable."),
        "inactive": _("The email or password is incorrect, or the account is unavailable."),
    }

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class ChangePasswordForm(forms.Form):
    old_password = forms.CharField(
        label=_("Current password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "autofocus": True}),
    )
    new_password = forms.CharField(
        label=_("New password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_("At least 10 characters; not a common or purely numeric password."),
    )
    confirm_password = forms.CharField(
        label=_("Confirm new password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        data = super().clean()
        if data.get("new_password") and data.get("new_password") != data.get("confirm_password"):
            self.add_error("confirm_password", _("The two passwords do not match."))
        return data


class PasswordResetRequestForm(PasswordResetForm):
    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )


class PasswordResetConfirmForm(SetPasswordForm):
    pass

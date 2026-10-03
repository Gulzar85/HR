from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _


class ProfileForm(forms.Form):
    first_name = forms.CharField(label=_("First name"), max_length=150)
    last_name = forms.CharField(label=_("Last name"), max_length=150)
    email = forms.EmailField(label=_("Email"), max_length=254)
    theme_mode = forms.ChoiceField(
        label=_("Appearance"),
        choices=[("system", _("Match my device")), ("light", _("Light")), ("dark", _("Dark"))],
    )

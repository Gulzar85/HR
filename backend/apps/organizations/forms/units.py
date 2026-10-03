"""Create / edit / status / move forms for every organization type.

Forms only collect and validate input; the services decide (hierarchy, scope, status rules).
Parent selects are named after the parent *type key* so the cascade endpoint and services agree.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from ..hierarchy import ORG_TYPES
from ..models import (
    Area,
    Company,
    CorporateLocation,
    Department,
    Division,
    Region,
    Restaurant,
    RestaurantStatus,
    StructureType,
)
from .cascade import CascadeMixin, org_choice_field

DATE = forms.DateInput(attrs={"type": "date"})


class OrgModelForm(CascadeMixin, forms.ModelForm):
    parent_key: str | None = None  # name of the parent select (create only)

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if "effective_from" in self.fields:
            self.fields["effective_from"].required = False
            self.fields["effective_from"].help_text = _("Defaults to today.")
        self.setup_org_fields(user)

    def parent(self):
        return self.cleaned_data.get(self.parent_key) if self.parent_key else None

    def service_data(self) -> dict[str, Any]:
        skip = set(ORG_TYPES) | {"status"}
        return {k: v for k, v in self.cleaned_data.items() if k not in skip}


# ------------------------------------------------------------------ company
class CompanyForm(OrgModelForm):
    class Meta:
        model = Company
        fields = [
            "name", "legal_name", "registration_number", "tax_number", "description",
            "address", "phone", "email", "website", "theme_key", "effective_from",
        ]  # fmt: skip
        widgets = {
            "effective_from": DATE,
            "description": forms.Textarea(attrs={"rows": 3}),
            "address": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {"theme_key": _("Optional reference to a theme managed by the Theme Engine.")}


class CompanyEditForm(CompanyForm):
    class Meta(CompanyForm.Meta):
        fields = [f for f in CompanyForm.Meta.fields if f != "effective_from"]


# ----------------------------------------------------------------- division
class DivisionForm(OrgModelForm):
    parent_key = "company"
    company = org_choice_field("company")

    class Meta:
        model = Division
        fields = ["name", "structure_type", "description", "effective_from"]
        widgets = {"effective_from": DATE, "description": forms.Textarea(attrs={"rows": 3})}
        help_texts = {
            "structure_type": _("Decides which units can be created under this division.")
        }


class DivisionEditForm(OrgModelForm):
    class Meta:
        model = Division
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


# --------------------------------------------------------- corporate location
class CorporateLocationForm(OrgModelForm):
    parent_key = "division"
    division = org_choice_field("division", label=_("Corporate division"))

    class Meta:
        model = CorporateLocation
        fields = [
            "name",
            "city",
            "city_code",
            "address",
            "phone",
            "email",
            "description",
            "effective_from",
        ]
        widgets = {
            "effective_from": DATE,
            "description": forms.Textarea(attrs={"rows": 3}),
            "address": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {
            "city_code": _("3 letters, e.g. LHR. Becomes part of the code and cannot change.")
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["division"].queryset = self.fields["division"].queryset.filter(
            structure_type=StructureType.CORPORATE
        )


class CorporateLocationEditForm(OrgModelForm):
    class Meta:
        model = CorporateLocation
        fields = ["name", "city", "address", "phone", "email", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "address": forms.Textarea(attrs={"rows": 2}),
        }


# --------------------------------------------------------------- department
class DepartmentForm(OrgModelForm):
    parent_key = "corporate_location"
    corporate_location = org_choice_field("corporate_location")

    class Meta:
        model = Department
        fields = ["name", "short_code", "description", "effective_from"]
        widgets = {"effective_from": DATE, "description": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"short_code": _("e.g. HR. The code becomes DEPT-<city>-<short code>.")}


class DepartmentEditForm(OrgModelForm):
    class Meta:
        model = Department
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


# ------------------------------------------------------------------- region
class RegionForm(OrgModelForm):
    parent_key = "division"
    division = org_choice_field("division", label=_("Operations division"))

    class Meta:
        model = Region
        fields = ["name", "description", "effective_from"]
        widgets = {"effective_from": DATE, "description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["division"].queryset = self.fields["division"].queryset.filter(
            structure_type=StructureType.OPERATIONS
        )


class RegionEditForm(OrgModelForm):
    class Meta:
        model = Region
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


# --------------------------------------------------------------------- area
class AreaForm(OrgModelForm):
    parent_key = "region"
    region = org_choice_field("region")

    class Meta:
        model = Area
        fields = ["name", "description", "effective_from"]
        widgets = {"effective_from": DATE, "description": forms.Textarea(attrs={"rows": 3})}


class AreaEditForm(RegionEditForm):
    class Meta(RegionEditForm.Meta):
        model = Area


# --------------------------------------------------------------- restaurant
class RestaurantForm(OrgModelForm):
    parent_key = "area"
    cascades = {"area": "region"}
    region = org_choice_field("region", label=_("Region"), required=False)
    area = org_choice_field("area")
    status = forms.ChoiceField(
        label=_("Initial status"),
        choices=[
            (RestaurantStatus.PLANNED, "Planned"),
            (RestaurantStatus.ACTIVE, "Active (open now)"),
        ],
        initial=RestaurantStatus.PLANNED,
    )

    field_order = [
        "region",
        "area",
        "name",
        "short_name",
        "city",
        "city_code",
        "status",
        "opening_date",
    ]

    class Meta:
        model = Restaurant
        fields = [
            "name", "short_name", "city", "city_code", "opening_date", "address",
            "latitude", "longitude", "phone", "email", "description", "effective_from",
        ]  # fmt: skip
        widgets = {
            "opening_date": DATE, "effective_from": DATE,
            "description": forms.Textarea(attrs={"rows": 2}), "address": forms.Textarea(attrs={"rows": 2}),
        }  # fmt: skip
        help_texts = {
            "city_code": _(
                "3 letters, e.g. LHR. The code becomes RST-<city>-NNN and cannot change."
            )
        }


class RestaurantEditForm(OrgModelForm):
    class Meta:
        model = Restaurant
        fields = [
            "name", "short_name", "city", "opening_date", "address",
            "latitude", "longitude", "phone", "email", "description",
        ]  # fmt: skip
        widgets = {
            "opening_date": DATE,
            "description": forms.Textarea(attrs={"rows": 2}),
            "address": forms.Textarea(attrs={"rows": 2}),
        }


# ------------------------------------------------------------ status & move
class StatusChangeForm(forms.Form):
    action = forms.ChoiceField(label=_("Action"))
    effective_date = forms.DateField(
        label=_("Effective date"), required=False, widget=DATE, help_text=_("Defaults to today.")
    )
    reason = forms.CharField(
        label=_("Reason"), max_length=255, widget=forms.Textarea(attrs={"rows": 2})
    )

    def __init__(self, *args: Any, actions: list[str], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["action"].choices = [(a, a.replace("_", " ").capitalize()) for a in actions]


class MoveForm(CascadeMixin, forms.Form):
    effective_date = forms.DateField(
        label=_("Move effective from"),
        required=False,
        widget=DATE,
        help_text=_("Defaults to today. History keeps the previous parent."),
    )
    reason = forms.CharField(
        label=_("Reason"), max_length=255, widget=forms.Textarea(attrs={"rows": 2})
    )

    def __init__(self, *args: Any, key: str, obj: Any, user: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        t = ORG_TYPES[key]
        parent_key = t.parent_key
        if key == "restaurant":
            self.cascades = {"area": "region"}
            self.fields["region"] = org_choice_field("region", required=False)
        self.fields[parent_key] = org_choice_field(
            parent_key, label=_("New ") + ORG_TYPES[parent_key].label.lower()
        )  # type: ignore[index]
        self.order_fields(["region", str(parent_key), "effective_date", "reason"])
        self.setup_org_fields(user)
        qs = self.fields[parent_key].queryset.exclude(pk=getattr(obj, t.parent_field + "_id"))  # type: ignore[operator]
        if t.parent_structure:
            qs = qs.filter(structure_type=t.parent_structure)
        self.fields[parent_key].queryset = qs
        self.parent_key = parent_key


FORMS = {
    "company": (CompanyForm, CompanyEditForm),
    "division": (DivisionForm, DivisionEditForm),
    "corporate_location": (CorporateLocationForm, CorporateLocationEditForm),
    "department": (DepartmentForm, DepartmentEditForm),
    "region": (RegionForm, RegionEditForm),
    "area": (AreaForm, AreaEditForm),
    "restaurant": (RestaurantForm, RestaurantEditForm),
}

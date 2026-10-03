"""Reusable cascading organization selects (Region -> Area -> Restaurant, Location -> Department).

Declare ``cascades = {"area": "region"}`` on a form: when the *region* select changes, HTMX loads the
scoped options for *area* from ``organizations:options``. The server still validates the final
choice (child must belong to the chosen parent and be in the user's scope); JavaScript only improves
usability.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django import forms
from django.urls import reverse

from ..hierarchy import ORG_TYPES, ancestor_paths
from ..selectors import visible_units


class OrgChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj) -> str:
        return f"{obj.code} · {obj.name}"


def org_choice_field(
    key: str, *, label: str | None = None, required: bool = True
) -> OrgChoiceField:
    return OrgChoiceField(
        queryset=ORG_TYPES[key].model._default_manager.none(),
        label=label or ORG_TYPES[key].label,
        required=required,
    )


class CascadeMixin:
    """Mixin for forms whose org-select fields are named after the org type key."""

    cascades: ClassVar[dict[str, str]] = {}  # child field -> parent field
    blank_label: ClassVar[str] = "---------"

    def setup_org_fields(self, user: Any, *, live_only: bool = True) -> None:
        fields = self.fields  # type: ignore[attr-defined]
        for name, field in fields.items():
            if isinstance(field, forms.ModelChoiceField) and name in ORG_TYPES:
                qs = visible_units(user, name)
                if live_only:
                    qs = qs.filter(status__in=["planned", "active", "temporarily_closed"])
                field.queryset = qs
        for child, parent in self.cascades.items():
            if child not in fields or parent not in fields:
                continue
            fields[parent].widget.attrs.update(
                {
                    "hx-get": reverse("organizations:options", args=[child]),
                    "hx-target": f"#id_{child}",
                    "hx-trigger": "change",
                    "hx-swap": "innerHTML",
                    "hx-params": parent,
                }
            )
            parent_value = self._bound_value(parent)  # type: ignore[attr-defined]
            if parent_value:
                path = ancestor_paths(child)[parent]
                fields[child].queryset = fields[child].queryset.filter(
                    **{f"{path}_id": parent_value}
                )

    def _bound_value(self, name: str) -> str | None:
        data = getattr(self, "data", None)
        value = data.get(name) if data else None
        if not value:
            initial = getattr(self, "initial", {}).get(name)
            value = str(getattr(initial, "pk", initial)) if initial else None
        try:
            return str(uuid.UUID(str(value))) if value else None
        except ValueError:
            return None

    def clean(self):
        cleaned = super().clean()  # type: ignore[misc]
        for child, parent in self.cascades.items():
            c, p = cleaned.get(child), cleaned.get(parent)
            if c is None or p is None:
                continue
            path = ancestor_paths(child)[parent]
            if (
                not ORG_TYPES[child]
                .model._default_manager.filter(pk=c.pk, **{f"{path}_id": p.pk})
                .exists()
            ):
                self.add_error(
                    child,
                    f"Choose a {ORG_TYPES[child].label.lower()} within the selected {ORG_TYPES[parent].label.lower()}.",
                )  # type: ignore[attr-defined]
        return cleaned

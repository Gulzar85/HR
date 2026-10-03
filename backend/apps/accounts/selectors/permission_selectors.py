from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.contrib.auth.models import Permission

from ..services.permission_service import PermissionService, perm_label


def grouped_permissions(selected_ids: Iterable[int] = ()) -> list[dict[str, Any]]:
    """Assignable permissions grouped by app + model, for the role/group permission matrix."""
    selected = set(selected_ids)
    groups: dict[str, dict[str, Any]] = {}
    for p in PermissionService.assignable_permissions():
        ct = p.content_type
        key = f"{ct.app_label}.{ct.model}"
        g = groups.setdefault(
            key,
            {
                "title": f"{ct.app_label.replace('_', ' ').title()} · {ct.model.replace('_', ' ')}",
                "items": [],
            },
        )
        g["items"].append(
            {"id": p.pk, "name": p.name, "label": perm_label(p), "checked": p.pk in selected}
        )
    return list(groups.values())


def permissions_from_ids(ids: Iterable[int]) -> list[Permission]:
    return list(PermissionService.assignable_permissions().filter(pk__in=list(ids)))

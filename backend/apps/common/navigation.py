"""Sidebar navigation registry.

Each app registers its own menu items in ``AppConfig.ready()``; the layout never hard-codes
modules. Visibility is a *display* convenience only - views enforce permissions themselves.

    register_nav_item("administration", "Users", "accounts:user_list", icon="users",
                      permission="accounts.view_user", key="users", order=10)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True)
class NavItem:
    section: str
    label: str
    url_name: str
    icon: str = "circle"
    permission: str | None = None  # None = any authenticated user
    key: str = ""
    order: int = 100


@dataclass
class NavSection:
    key: str
    label: str
    order: int = 100
    items: list[NavItem] = field(default_factory=list)


_SECTIONS: dict[str, NavSection] = {}


def register_nav_section(key: str, label: str, order: int = 100) -> None:
    _SECTIONS.setdefault(key, NavSection(key, label, order))


def register_nav_item(
    section: str,
    label: str,
    url_name: str,
    *,
    icon: str = "circle",
    permission: str | None = None,
    key: str = "",
    order: int = 100,
) -> None:
    sec = _SECTIONS.setdefault(section, NavSection(section, section.title()))
    item = NavItem(section, label, url_name, icon, permission, key or url_name, order)
    sec.items = [i for i in sec.items if i.key != item.key] + [item]


def navigation_for(user) -> list[dict]:
    """Sections/items visible to ``user`` (already resolved to URLs)."""
    if not getattr(user, "is_authenticated", False):
        return []
    result = []
    for sec in sorted(_SECTIONS.values(), key=lambda s: s.order):
        items = []
        for item in sorted(sec.items, key=lambda i: i.order):
            if item.permission and not user.has_perm(item.permission):
                continue
            try:
                url = reverse(item.url_name)
            except NoReverseMatch:
                continue
            items.append({"label": item.label, "url": url, "icon": item.icon, "key": item.key})
        if items:
            result.append({"key": sec.key, "label": sec.label, "items": items})
    return result


def context_processor(request) -> dict:
    return {"navigation": navigation_for(getattr(request, "user", None))}


register_nav_section("main", "", order=0)
register_nav_section("administration", "Administration", order=50)
register_nav_section("account", "My account", order=90)
register_nav_item("main", "Home", "home", icon="layout-dashboard", key="home", order=0)
register_nav_item(
    "account", "Profile", "accounts:profile", icon="user-round", key="profile", order=10
)
register_nav_item(
    "account", "Sessions", "accounts:sessions", icon="monitor-smartphone", key="sessions", order=20
)

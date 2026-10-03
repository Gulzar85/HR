"""Company screens. Behaviour is generic (views/base.py); this module only declares what differs."""

from __future__ import annotations

from ..base import (
    Column,
    OrgCreateView,
    OrgDetailView,
    OrgListView,
    OrgStatusView,
    OrgUpdateView,
)

KEY = "company"


class _Company:
    type_key = KEY
    columns = [
        Column("Company", "unit"),
        Column("Legal name", "text", "legal_name", hide_sm=True),
        Column("Status", "status"),
        Column("Effective from", "date", "effective_from", hide_sm=True),
    ]
    detail_fields = [
        ("Legal name", "legal_name"),
        ("Registration no.", "registration_number"),
        ("Tax number (NTN)", "tax_number"),
        ("Address", "address"),
        ("Phone", "phone"),
        ("Email", "email"),
        ("Website", "website"),
        ("Theme reference", "theme_key"),
    ]


class CompanyListView(_Company, OrgListView):
    pass


class CompanyDetailView(_Company, OrgDetailView):
    pass


class CompanyCreateView(_Company, OrgCreateView):
    pass


class CompanyUpdateView(_Company, OrgUpdateView):
    pass


class CompanyStatusView(_Company, OrgStatusView):
    pass

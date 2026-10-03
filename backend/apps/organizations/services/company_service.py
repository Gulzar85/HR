from __future__ import annotations

from apps.common.services import generate_code

from .organization_service import OrganizationService, OrgUnitService


@OrganizationService.register
class CompanyService(OrgUnitService):
    type_key = "company"
    editable_fields = (
        "name", "description", "legal_name", "registration_number", "tax_number",
        "address", "phone", "email", "website", "theme_key",
    )  # fmt: skip

    @classmethod
    def generate_code(cls, fields, parent) -> str:
        return generate_code("CMP", width=3)  # CMP-001

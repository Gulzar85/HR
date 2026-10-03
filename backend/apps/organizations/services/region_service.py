from __future__ import annotations

from apps.common.services import generate_code

from .organization_service import OrganizationService, OrgUnitService


@OrganizationService.register
class RegionService(OrgUnitService):
    type_key = "region"

    @classmethod
    def generate_code(cls, fields, parent) -> str:
        return generate_code("REG", width=3)  # REG-001

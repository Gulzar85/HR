from __future__ import annotations

from apps.common.services import generate_code

from .organization_service import OrganizationService, OrgUnitService


@OrganizationService.register
class AreaService(OrgUnitService):
    type_key = "area"

    @classmethod
    def generate_code(cls, fields, parent) -> str:
        return generate_code("AREA", width=3)  # AREA-001

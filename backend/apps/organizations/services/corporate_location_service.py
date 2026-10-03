from __future__ import annotations

from apps.common.services import generate_code

from .organization_service import OrganizationService, OrgUnitService


@OrganizationService.register
class CorporateLocationService(OrgUnitService):
    type_key = "corporate_location"
    editable_fields = ("name", "description", "city", "address", "phone", "email")
    create_only_fields = ("city_code",)

    @classmethod
    def generate_code(cls, fields, parent) -> str:
        return generate_code("LOC", scope=fields["city_code"], width=3)  # LOC-LHR-001

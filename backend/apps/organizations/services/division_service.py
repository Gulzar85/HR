from __future__ import annotations

from typing import ClassVar

from apps.common.services import generate_code

from ..models import StructureType
from .organization_service import OrganizationService, OrgUnitService


@OrganizationService.register
class DivisionService(OrgUnitService):
    type_key = "division"
    create_only_fields = ("structure_type",)
    ABBREVIATIONS: ClassVar[dict[str, str]] = {
        StructureType.CORPORATE: "CORP",
        StructureType.OPERATIONS: "OPS",
    }

    @classmethod
    def generate_code(cls, fields, parent) -> str:
        return generate_code("DIV", scope=cls.ABBREVIATIONS[fields["structure_type"]], width=3)

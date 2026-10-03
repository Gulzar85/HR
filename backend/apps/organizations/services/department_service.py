from __future__ import annotations

from apps.common.exceptions import ConflictException

from ..models import Department
from .organization_service import OrganizationService, OrgUnitService


@OrganizationService.register
class DepartmentService(OrgUnitService):
    type_key = "department"
    create_only_fields = ("short_code",)

    @classmethod
    def generate_code(cls, fields, parent) -> str:
        return f"DEPT-{parent.city_code}-{fields['short_code']}"  # DEPT-LHR-HR

    @classmethod
    def extra_checks(cls, obj, parent) -> None:
        clash = Department.objects.filter(location=parent, short_code=obj.short_code).exclude(
            pk=obj.pk
        )
        if clash.exists():
            raise ConflictException(
                f"{parent.name} already has a department with short code {obj.short_code}.",
                details={"short_code": ["Already used at this location."]},
            )

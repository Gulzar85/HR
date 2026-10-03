"""Employee API serializers - one per purpose (no catch-all serializer).

Field-level sensitivity is enforced **here, server-side** (ADR-021): the request user's permissions
are read from ``context["request"]`` and sensitive fields are omitted (not nulled) when the user may
not see them. Identifier values are always masked unless the view explicitly asks for a revealed
representation *and* the user holds both identifier permissions.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .. import permissions as P
from ..models import (
    Address,
    AddressType,
    Contact,
    ContactType,
    EmergencyContact,
    Employee,
    EmployeeIdentifier,
    EmployeeStatus,
    Gender,
    IdentifierType,
    RelationshipType,
    TimelineEntry,
    VerificationStatus,
)


def _can(context: dict[str, Any], perm: str) -> bool:
    request = context.get("request")
    return bool(request and request.user.has_perm(perm))


class PersonSummarySerializer(serializers.Serializer):
    first_name = serializers.CharField()
    middle_name = serializers.CharField()
    last_name = serializers.CharField()
    preferred_name = serializers.CharField()
    full_name = serializers.CharField()
    display_name = serializers.CharField()


class EmployeeListSerializer(serializers.ModelSerializer):
    """Minimum data: code, names, status, primary email/mobile, account flag. No sensitive data."""

    person = PersonSummarySerializer(read_only=True)
    email = serializers.SerializerMethodField()
    mobile = serializers.SerializerMethodField()
    has_user_account = serializers.BooleanField(read_only=True)

    class Meta:
        model = Employee
        fields = [
            "id",
            "code",
            "employee_status",
            "person",
            "email",
            "mobile",
            "has_user_account",
            "created_at",
        ]
        read_only_fields = fields

    def _primary(self, obj, kind: str) -> str | None:
        contacts = getattr(obj, "primary_contacts", None)
        if contacts is None:
            contacts = [c for c in obj.contacts.all() if c.is_primary]
        return next((c.value for c in contacts if c.contact_type == kind), None)

    def get_email(self, obj) -> str | None:
        return self._primary(obj, ContactType.EMAIL)

    def get_mobile(self, obj) -> str | None:
        return self._primary(obj, ContactType.MOBILE)


class EmployeeContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ["id", "contact_type", "value", "label", "is_primary", "is_verified", "created_at"]
        read_only_fields = ["id", "is_verified", "created_at"]


class EmployeeAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id", "address_type", "address_line_1", "address_line_2", "city", "state_province",
            "postal_code", "country", "is_primary", "effective_from", "effective_to",
        ]  # fmt: skip
        read_only_fields = ["id", "is_primary", "effective_to"]


class EmergencyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyContact
        fields = [
            "id",
            "name",
            "relationship",
            "phone",
            "alternative_phone",
            "email",
            "address",
            "is_primary",
        ]
        read_only_fields = ["id"]


class EmployeeIdentifierSerializer(serializers.ModelSerializer):
    """``value`` is masked unless ``context["reveal"]`` and the user holds both identifier perms."""

    value = serializers.SerializerMethodField()
    masked = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeIdentifier
        fields = [
            "id", "identifier_type", "value", "masked", "issuing_country", "issue_date",
            "expiry_date", "verification_status", "is_primary",
        ]  # fmt: skip
        read_only_fields = fields

    def _revealed(self) -> bool:
        return bool(
            self.context.get("reveal")
            and _can(self.context, P.VIEW_IDENTIFIERS)
            and _can(self.context, P.VIEW_SENSITIVE_IDENTITY)
        )

    def get_value(self, obj) -> str:
        return obj.value if self._revealed() else obj.masked_value

    def get_masked(self, obj) -> bool:
        return not self._revealed()


class IdentifierWriteSerializer(serializers.Serializer):
    identifier_type = serializers.ChoiceField(choices=IdentifierType.choices)
    value = serializers.CharField(max_length=64, write_only=True)
    issuing_country = serializers.CharField(max_length=2, required=False, allow_blank=True)
    issue_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    is_primary = serializers.BooleanField(required=False)


class EmployeeTimelineSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = TimelineEntry
        fields = [
            "id",
            "event_type",
            "summary",
            "description",
            "occurred_at",
            "source_app",
            "actor",
        ]
        read_only_fields = fields

    def get_actor(self, obj) -> str | None:
        return obj.actor.display_name if obj.actor_id else None


class EmployeeDetailSerializer(EmployeeListSerializer):
    """List fields + sections the caller may see. Sections the caller may not see are *omitted*."""

    class Meta(EmployeeListSerializer.Meta):
        fields = [*EmployeeListSerializer.Meta.fields, "archived_at", "updated_at"]
        read_only_fields = fields

    def to_representation(self, obj):
        data = super().to_representation(obj)
        ctx = self.context
        data["contacts"] = EmployeeContactSerializer(obj.contacts.all(), many=True).data
        if _can(ctx, P.VIEW_SENSITIVE_IDENTITY):
            p = obj.person
            data["person"].update(
                date_of_birth=p.date_of_birth.isoformat() if p.date_of_birth else None,
                gender=p.gender or None,
                nationality=p.nationality or None,
                has_photo=bool(p.profile_photo),
            )
        if _can(ctx, P.VIEW_SENSITIVE_CONTACTS):
            data["addresses"] = EmployeeAddressSerializer(obj.addresses.all(), many=True).data
        if _can(ctx, P.VIEW_EMERGENCY_CONTACTS):
            data["emergency_contacts"] = EmergencyContactSerializer(
                obj.emergency_contacts.all(), many=True
            ).data
        if _can(ctx, P.VIEW_IDENTIFIERS):
            data["identifiers"] = EmployeeIdentifierSerializer(
                obj.identifiers.all(), many=True, context=ctx
            ).data
        if _can(ctx, P.LINK_USER):
            data["user"] = (
                {"id": str(obj.user_id), "email": obj.user.email} if obj.user_id else None
            )
        return data


class PersonWriteSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=80)
    middle_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=80)
    preferred_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=[("", ""), *Gender.choices], required=False, allow_blank=True
    )
    nationality = serializers.CharField(max_length=2, required=False, allow_blank=True)


class ContactWriteSerializer(serializers.Serializer):
    contact_type = serializers.ChoiceField(choices=ContactType.choices)
    value = serializers.CharField(max_length=160)
    label = serializers.CharField(max_length=60, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False)


class AddressWriteSerializer(serializers.Serializer):
    address_type = serializers.ChoiceField(choices=AddressType.choices)
    address_line_1 = serializers.CharField(max_length=200)
    address_line_2 = serializers.CharField(max_length=200, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    state_province = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country = serializers.CharField(max_length=2, required=False, allow_blank=True)
    effective_from = serializers.DateField(required=False, allow_null=True)


class EmergencyWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    relationship = serializers.ChoiceField(choices=RelationshipType.choices)
    phone = serializers.CharField(max_length=40)
    alternative_phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False)


class EmployeeCreateSerializer(serializers.Serializer):
    person = PersonWriteSerializer()
    employee_status = serializers.ChoiceField(
        choices=[EmployeeStatus.ACTIVE, EmployeeStatus.INACTIVE], required=False
    )
    contacts = ContactWriteSerializer(many=True, required=False)
    addresses = AddressWriteSerializer(many=True, required=False)
    emergency_contacts = EmergencyWriteSerializer(many=True, required=False)
    identifiers = IdentifierWriteSerializer(many=True, required=False)
    confirm_duplicates = serializers.BooleanField(required=False, default=False)


class EmployeeUpdateSerializer(serializers.Serializer):
    """Person fields only. Status, account link and child records have their own endpoints."""

    first_name = serializers.CharField(max_length=80, required=False)
    middle_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=80, required=False)
    preferred_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=[("", ""), *Gender.choices], required=False, allow_blank=True
    )
    nationality = serializers.CharField(max_length=2, required=False, allow_blank=True)


class StatusChangeSerializer(serializers.Serializer):
    employee_status = serializers.ChoiceField(choices=EmployeeStatus.choices)
    reason = serializers.CharField(max_length=255)


class VerificationSerializer(serializers.Serializer):
    verification_status = serializers.ChoiceField(choices=VerificationStatus.choices)


class LinkUserSerializer(serializers.Serializer):
    email = serializers.EmailField()

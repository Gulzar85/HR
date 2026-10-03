from __future__ import annotations

from typing import Any

from rest_framework import serializers

from ..hierarchy import ORG_TYPES, get_parent, org_type_of
from ..models import OrganizationHistory, StructureType
from ..services import OrganizationService

BASE_FIELDS = ["id", "code", "name", "status", "effective_from", "effective_to", "description"]


def _parent_repr(obj: Any) -> dict[str, Any] | None:
    parent = get_parent(obj)
    if parent is None:
        return None
    return {
        "type": org_type_of(parent).key,
        "id": str(parent.pk),
        "code": parent.code,
        "name": parent.name,
    }


def read_serializer(key: str) -> type[serializers.ModelSerializer]:
    t = ORG_TYPES[key]
    service = OrganizationService.for_type(key)
    extra = [
        f for f in service.editable_fields + service.create_only_fields if f not in BASE_FIELDS
    ]

    class ReadSerializer(serializers.ModelSerializer):
        type = serializers.SerializerMethodField()
        parent = serializers.SerializerMethodField()

        class Meta:
            model = t.model
            fields = [*BASE_FIELDS, "type", "parent", *extra]
            read_only_fields = fields

        def get_type(self, obj) -> str:
            return key

        def get_parent(self, obj):
            return _parent_repr(obj)

    ReadSerializer.__name__ = f"{t.model.__name__}ReadSerializer"
    return ReadSerializer


def write_serializer(key: str, *, create: bool) -> type[serializers.ModelSerializer]:
    t = ORG_TYPES[key]
    service = OrganizationService.for_type(key)
    fields = list(service.editable_fields) + (
        list(service.create_only_fields) + ["effective_from"] if create else []
    )
    attrs: dict[str, Any] = {}
    if create and t.parent_key:
        attrs["parent_id"] = serializers.UUIDField(
            help_text=f"UUID of the parent {ORG_TYPES[t.parent_key].label.lower()}."
        )
    if create:
        attrs["status"] = serializers.ChoiceField(
            choices=sorted(service.initial_statuses), required=False, help_text="Initial status."
        )
    if create and key == "division":
        attrs["structure_type"] = serializers.ChoiceField(choices=StructureType.choices)

    meta = type("Meta", (), {"model": t.model, "fields": fields + list(attrs)})
    cls = type(
        f"{t.model.__name__}{'Create' if create else 'Update'}Serializer",
        (serializers.ModelSerializer,),
        {**attrs, "Meta": meta},
    )
    return cls


class StatusSerializer(serializers.Serializer):
    action = serializers.CharField()
    reason = serializers.CharField(max_length=255)
    effective_date = serializers.DateField(required=False, allow_null=True)


class MoveSerializer(serializers.Serializer):
    parent_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=255)
    effective_date = serializers.DateField(required=False, allow_null=True)


class HistorySerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationHistory
        fields = [
            "id",
            "event",
            "effective_date",
            "before",
            "after",
            "reason",
            "actor",
            "timestamp",
        ]

    def get_actor(self, obj) -> str | None:
        return obj.actor.email if obj.actor_id else None

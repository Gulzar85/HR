"""Business-code support: per-(prefix, scope, year) sequences and an immutable ``code`` field."""

from django.core.exceptions import ValidationError
from django.db import models


class CodeSequence(models.Model):
    """Counter row backing ``apps.common.services.codes.generate_code``."""

    prefix = models.CharField(max_length=16)
    scope = models.CharField(max_length=32, blank=True, default="")
    year = models.PositiveSmallIntegerField(default=0)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["prefix", "scope", "year"], name="uniq_code_sequence")
        ]

    def __str__(self) -> str:
        return f"{self.prefix}/{self.scope}/{self.year}={self.last_value}"


class BusinessCodeModel(models.Model):
    """Abstract: a unique, immutable, human-readable ``code`` (e.g. EMP-000001).

    The code is assigned once (by a service via ``generate_code``) and can never change.
    """

    code = models.CharField(max_length=40, unique=True, editable=False)
    _original_code: str | None = None

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        original = getattr(self, "_original_code", None)
        if original and self.code != original:
            raise ValidationError("Business codes are immutable.", code="immutable_code")
        if not self.code:
            raise ValidationError("A business code is required.", code="missing_code")
        super().save(*args, **kwargs)
        self._original_code = self.code

    @classmethod
    def from_db(cls, db, field_names, values, *args, **kwargs):  # type: ignore[override]
        instance = super().from_db(db, field_names, values, *args, **kwargs)
        instance._original_code = instance.__dict__.get("code")  # type: ignore[assignment]
        return instance

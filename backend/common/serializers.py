import re
from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

EXPLICIT_OFFSET_PATTERN = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")


class ExplicitTimezoneDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value: Any) -> Any:
        if not isinstance(value, str) or not EXPLICIT_OFFSET_PATTERN.search(value):
            raise serializers.ValidationError("Datetime must include an explicit UTC offset")
        return super().to_internal_value(value)


class StrictSerializer(serializers.Serializer[Any]):
    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        initial_data = getattr(self, "initial_data", {})
        if isinstance(initial_data, Mapping):
            unknown_fields = set(initial_data) - set(self.fields)
            if unknown_fields:
                raise serializers.ValidationError(
                    {field_name: "Unknown field" for field_name in sorted(unknown_fields)}
                )
        return attrs


class ErrorResponseSerializer(serializers.Serializer[Any]):
    detail = serializers.CharField()

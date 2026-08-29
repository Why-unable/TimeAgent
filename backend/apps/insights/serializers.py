from rest_framework import serializers

from apps.insights.models import TemporalInsight


class TemporalInsightSerializer(serializers.ModelSerializer[TemporalInsight]):
    class Meta:
        model = TemporalInsight
        fields = [
            "id",
            "kind",
            "severity",
            "status",
            "title",
            "summary",
            "evidence",
            "deduplication_key",
            "detected_at",
            "expires_at",
            "snoozed_until",
            "acted_at",
            "attention_decision",
            "attention_reason",
            "attention_decided_at",
        ]


class TemporalInsightActionSerializer(serializers.Serializer[dict[str, object]]):
    action = serializers.ChoiceField(choices=["snooze", "dismiss", "actioned", "false_positive"])
    until = serializers.DateTimeField(required=False, allow_null=True)
    disable_kind = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs.get("disable_kind") and attrs.get("action") != "false_positive":
            raise serializers.ValidationError(
                {"disable_kind": "Only false_positive feedback can disable an insight kind"}
            )
        return attrs

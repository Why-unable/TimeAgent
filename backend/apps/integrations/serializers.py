from rest_framework import serializers

from apps.integrations.models import CalendarSyncConnection


class CalendarSyncConnectionSerializer(serializers.ModelSerializer[CalendarSyncConnection]):
    class Meta:
        model = CalendarSyncConnection
        fields = [
            "id",
            "provider_name",
            "calendar_name",
            "timezone",
            "enabled",
            "status",
            "last_synced_at",
            "last_error",
            "created_at",
            "updated_at",
        ]


class CalendarSyncConnectionWriteSerializer(serializers.Serializer[dict[str, object]]):
    provider_name = serializers.ChoiceField(choices=["ics"])
    account_reference = serializers.CharField(max_length=255)
    calendar_id = serializers.CharField(max_length=255)
    calendar_name = serializers.CharField(max_length=255)
    timezone = serializers.CharField(max_length=64)
    enabled = serializers.BooleanField(default=True)


class CalendarSyncRequestSerializer(serializers.Serializer[dict[str, object]]):
    starts_at_or_after = serializers.DateTimeField()
    starts_before = serializers.DateTimeField()


class CalendarSyncResultSerializer(serializers.Serializer[dict[str, object]]):
    connection_id = serializers.UUIDField()
    fetched_count = serializers.IntegerField(min_value=0)
    created_count = serializers.IntegerField(min_value=0)
    updated_count = serializers.IntegerField(min_value=0)
    cancelled_count = serializers.IntegerField(min_value=0)
    synced_at = serializers.DateTimeField()


class CalendarOAuthStartResultSerializer(serializers.Serializer[dict[str, object]]):
    authorization_url = serializers.CharField()
    expires_at = serializers.DateTimeField()


class CalendarOAuthCallbackQuerySerializer(serializers.Serializer[dict[str, object]]):
    code = serializers.CharField(required=False, allow_blank=False, max_length=4096)
    state = serializers.CharField(required=False, allow_blank=False, max_length=512)
    error = serializers.CharField(required=False, allow_blank=False, max_length=255)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        attrs = super().validate(attrs)
        if "error" in attrs:
            return attrs
        if "code" not in attrs or "state" not in attrs:
            raise serializers.ValidationError("OAuth callback requires code and state")
        return attrs

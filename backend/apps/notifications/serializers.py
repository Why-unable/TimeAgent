from rest_framework import serializers

from apps.notifications.models import (
    NotificationDelivery,
    NotificationPreference,
    WebPushSubscription,
)


class NotificationPreferenceSerializer(serializers.ModelSerializer[NotificationPreference]):
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = NotificationPreference
        fields = [
            "email",
            "reminder_console_enabled",
            "reminder_email_enabled",
            "reminder_web_push_enabled",
            "briefing_console_enabled",
            "briefing_email_enabled",
            "briefing_web_push_enabled",
            "updated_at",
        ]
        read_only_fields = ["email", "updated_at"]


class NotificationDeliverySerializer(serializers.ModelSerializer[NotificationDelivery]):
    class Meta:
        model = NotificationDelivery
        fields = [
            "id",
            "source_type",
            "source_id",
            "channel_type",
            "status",
            "subject",
            "scheduled_at",
            "queued_at",
            "sending_at",
            "sent_at",
            "failed_at",
            "attempt_count",
            "next_retry_at",
            "provider_message_id",
            "failure_code",
            "failure_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class WebPushConfigSerializer(serializers.Serializer[dict[str, object]]):
    configured = serializers.BooleanField()
    public_key = serializers.CharField(allow_blank=True)


class WebPushSubscriptionCreateSerializer(serializers.Serializer[dict[str, object]]):
    endpoint = serializers.URLField(max_length=2048)
    p256dh = serializers.CharField(max_length=4096)
    auth = serializers.CharField(max_length=4096)


class WebPushSubscriptionSerializer(serializers.ModelSerializer[WebPushSubscription]):
    endpoint_hint = serializers.SerializerMethodField()

    class Meta:
        model = WebPushSubscription
        fields = ["id", "endpoint_hint", "enabled", "last_used_at", "invalidated_at", "created_at"]
        read_only_fields = fields

    def get_endpoint_hint(self, instance: WebPushSubscription) -> str:
        return instance.endpoint[:32] + "…" if len(instance.endpoint) > 32 else instance.endpoint

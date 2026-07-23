from django.contrib import admin

from apps.notifications.models import (
    NotificationDelivery,
    NotificationPreference,
    WebPushSubscription,
)


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "id",
        "user",
        "source_type",
        "channel_type",
        "status",
        "attempt_count",
        "created_at",
    )
    list_filter = ("source_type", "channel_type", "status")
    search_fields = ("deduplication_key", "subject", "provider_message_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("user", "reminder_email_enabled", "briefing_email_enabled", "updated_at")


@admin.register(WebPushSubscription)
class WebPushSubscriptionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "user", "enabled", "last_used_at", "invalidated_at", "created_at")
    exclude = ("endpoint", "p256dh", "auth")

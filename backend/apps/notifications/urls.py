from django.urls import path

from apps.notifications.views import (
    CurrentNotificationPreferenceView,
    NotificationDeliveryDetailView,
    NotificationDeliveryListView,
    WebPushConfigView,
    WebPushSubscriptionDestroyView,
    WebPushSubscriptionListCreateView,
    WebPushSubscriptionUnsubscribeView,
)

urlpatterns = [
    path("notification-preferences/me/", CurrentNotificationPreferenceView.as_view()),
    path("notification-deliveries/", NotificationDeliveryListView.as_view()),
    path("notification-deliveries/<uuid:delivery_id>/", NotificationDeliveryDetailView.as_view()),
    path("web-push/config/", WebPushConfigView.as_view()),
    path("web-push/subscriptions/", WebPushSubscriptionListCreateView.as_view()),
    path(
        "web-push/subscriptions/unsubscribe/",
        WebPushSubscriptionUnsubscribeView.as_view(),
    ),
    path(
        "web-push/subscriptions/<uuid:subscription_id>/", WebPushSubscriptionDestroyView.as_view()
    ),
]

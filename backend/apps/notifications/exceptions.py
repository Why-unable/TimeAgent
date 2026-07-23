class NotificationError(RuntimeError):
    code = "notification_error"


class TransientNotificationError(NotificationError):
    code = "transient_notification_error"


class PermanentNotificationError(NotificationError):
    code = "permanent_notification_error"


class NotificationConfigurationError(PermanentNotificationError):
    code = "notification_configuration_error"


class NotificationProviderNotRegisteredError(NotificationConfigurationError):
    code = "notification_provider_not_registered"

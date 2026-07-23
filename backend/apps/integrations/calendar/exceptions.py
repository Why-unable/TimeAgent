class ExternalCalendarError(RuntimeError):
    pass


class ExternalCalendarAuthenticationError(ExternalCalendarError):
    pass


class ExternalCalendarRateLimitError(ExternalCalendarError):
    pass


class ExternalCalendarTemporaryError(ExternalCalendarError):
    pass


class ExternalCalendarPermanentError(ExternalCalendarError):
    pass


class ExternalCalendarUnsupportedOperation(ExternalCalendarPermanentError):
    pass


class ExternalCalendarNotConfigured(ExternalCalendarPermanentError):
    pass

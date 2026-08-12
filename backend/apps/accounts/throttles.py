from rest_framework.throttling import AnonRateThrottle


class AuthenticationThrottle(AnonRateThrottle):
    scope = "authentication"


class GuestAuthenticationThrottle(AnonRateThrottle):
    scope = "guest_authentication"

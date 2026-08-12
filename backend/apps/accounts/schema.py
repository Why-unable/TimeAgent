from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ActiveAccountSessionScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    target_class = "apps.accounts.authentication.ActiveAccountSessionAuthentication"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema: object) -> dict[str, str]:
        del auto_schema
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": settings.SESSION_COOKIE_NAME,
        }

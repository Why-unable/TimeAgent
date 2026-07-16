from django.conf import settings
from django.db import connections
from drf_spectacular.utils import extend_schema
from redis import Redis
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.health.serializers import LiveResponseSerializer, ReadyResponseSerializer


@extend_schema(responses=LiveResponseSerializer)
@api_view(["GET"])
def live(request: Request) -> Response:
    return Response({"status": "alive"})


@extend_schema(responses={200: ReadyResponseSerializer, 503: ReadyResponseSerializer})
@api_view(["GET"])
def ready(request: Request) -> Response:
    checks: dict[str, str] = {}

    try:
        connections["default"].ensure_connection()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
    try:
        redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
    finally:
        redis_client.close()

    is_ready = all(value == "ok" for value in checks.values())
    return Response(
        {"status": "ready" if is_ready else "not_ready", "checks": checks},
        status=200 if is_ready else 503,
    )

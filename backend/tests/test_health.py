from unittest.mock import Mock, patch

from django.test import Client


def test_live_does_not_check_dependencies() -> None:
    response = Client().get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@patch("apps.health.views.Redis.from_url")
@patch("apps.health.views.connections")
def test_ready_reports_healthy_dependencies(
    mock_connections: Mock, mock_redis_from_url: Mock
) -> None:
    redis_client = mock_redis_from_url.return_value
    redis_client.ping.return_value = True

    response = Client().get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok"},
    }
    mock_connections["default"].ensure_connection.assert_called_once_with()
    redis_client.close.assert_called_once_with()


@patch("apps.health.views.Redis.from_url")
@patch("apps.health.views.connections")
def test_ready_returns_503_when_dependency_fails(
    mock_connections: Mock, mock_redis_from_url: Mock
) -> None:
    mock_connections["default"].ensure_connection.side_effect = RuntimeError("database down")
    redis_client = mock_redis_from_url.return_value
    redis_client.ping.side_effect = RuntimeError("redis down")

    response = Client().get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "error", "redis": "error"},
    }

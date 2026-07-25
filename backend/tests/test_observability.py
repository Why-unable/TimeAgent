from django.test import Client


def test_request_id_is_echoed_and_metrics_are_exposed() -> None:
    client = Client()

    response = client.get("/health/live", HTTP_X_REQUEST_ID="phase10-check")
    metrics = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "phase10-check"
    assert metrics.status_code == 200
    assert b"django_http_requests" in metrics.content


def test_request_id_is_generated_when_not_supplied() -> None:
    response = Client().get("/health/live")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]

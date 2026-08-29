from datetime import UTC, datetime
from typing import Any, cast

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import Client

from apps.events.models import CalendarEvent, CalendarEventStatus

pytestmark = pytest.mark.django_db

EVENTS_URL = "/api/v1/events/"


@pytest.fixture(autouse=True)
def fixed_event_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.events.services.SystemClock.now_utc",
        lambda self: datetime(2026, 7, 19, 1, tzinfo=UTC),
    )


def create_user(username: str = "event-api-user") -> User:
    return get_user_model().objects.create_user(username=username)


def event_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Project review",
        "start_at": "2026-07-20T09:00:00+08:00",
        "end_at": "2026-07-20T10:00:00+08:00",
        "timezone": "Asia/Shanghai",
    }
    payload.update(changes)
    return payload


def authenticated_client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def create_event(client: Client, **changes: object) -> dict[str, Any]:
    response = client.post(
        EVENTS_URL,
        data=event_payload(**changes),
        content_type="application/json",
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


@pytest.mark.parametrize("method", ["get", "post"])
def test_event_collection_requires_authentication(method: str) -> None:
    client = Client()

    response = getattr(client, method)(EVENTS_URL)

    assert response.status_code in (401, 403)


def test_event_create_list_and_retrieve_are_user_scoped() -> None:
    user = create_user()
    other = create_user("event-api-other")
    client = authenticated_client(user)
    other_client = authenticated_client(other)
    created = create_event(client)
    create_event(other_client, title="Other event")

    list_response = client.get(
        EVENTS_URL,
        {
            "starts_before": "2026-07-20T11:00:00+08:00",
            "ends_after": "2026-07-20T08:00:00+08:00",
            "status": CalendarEventStatus.CONFIRMED,
        },
    )
    detail_response = client.get(f"{EVENTS_URL}{created['id']}/")
    hidden_response = other_client.get(f"{EVENTS_URL}{created['id']}/")

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]
    assert detail_response.status_code == 200
    assert detail_response.json()["start_at"] == "2026-07-20T01:00:00Z"
    assert hidden_response.status_code == 404


def test_event_patch_requires_current_version_and_reports_conflict() -> None:
    user = create_user()
    client = authenticated_client(user)
    created = create_event(client)
    detail_url = f"{EVENTS_URL}{created['id']}/"

    updated_response = client.patch(
        f"{detail_url}?expected_version=1",
        data={"title": "Updated review"},
        content_type="application/json",
    )
    stale_response = client.patch(
        f"{detail_url}?expected_version=1",
        data={"title": "Stale review"},
        content_type="application/json",
    )
    missing_version_response = client.patch(
        detail_url,
        data={"title": "Missing version"},
        content_type="application/json",
    )

    assert updated_response.status_code == 200
    assert updated_response.json()["version"] == 2
    assert stale_response.status_code == 409
    assert missing_version_response.status_code == 400
    assert CalendarEvent.objects.get(pk=created["id"]).title == "Updated review"


def test_event_delete_cancels_with_optimistic_lock() -> None:
    user = create_user()
    client = authenticated_client(user)
    created = create_event(client)
    detail_url = f"{EVENTS_URL}{created['id']}/"

    missing_version_response = client.delete(detail_url)
    stale_response = client.delete(f"{detail_url}?expected_version=2")
    response = client.delete(f"{detail_url}?expected_version=1")

    assert missing_version_response.status_code == 400
    assert stale_response.status_code == 409
    assert response.status_code == 204
    event = CalendarEvent.objects.get(pk=created["id"])
    assert event.status == CalendarEventStatus.CANCELLED
    assert event.version == 2


def test_ended_event_update_and_cancel_return_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()
    client = authenticated_client(user)
    created = create_event(client)
    detail_url = f"{EVENTS_URL}{created['id']}/"
    monkeypatch.setattr(
        "apps.events.services.SystemClock.now_utc",
        lambda self: datetime(2026, 7, 20, 3, tzinfo=UTC),
    )

    update_response = client.patch(
        f"{detail_url}?expected_version=1",
        data={"title": "Too late"},
        content_type="application/json",
    )
    cancel_response = client.delete(f"{detail_url}?expected_version=1")

    assert update_response.status_code == 409
    assert cancel_response.status_code == 409
    assert update_response.json()["detail"] == "已结束的日程只读，不能修改或取消"


def test_event_api_requires_explicit_offsets_and_valid_ranges() -> None:
    client = authenticated_client(create_user())

    naive_response = client.post(
        EVENTS_URL,
        data=event_payload(start_at="2026-07-20T09:00:00"),
        content_type="application/json",
    )
    invalid_range_response = client.post(
        EVENTS_URL,
        data=event_payload(end_at="2026-07-20T09:00:00+08:00"),
        content_type="application/json",
    )

    assert naive_response.status_code == 400
    assert invalid_range_response.status_code == 400


def test_event_api_rejects_unknown_write_fields() -> None:
    client = authenticated_client(create_user())

    response = client.post(
        EVENTS_URL,
        data=event_payload(version=99),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "version" in response.json()


def test_event_api_cannot_forge_or_mutate_provider_identity() -> None:
    client = authenticated_client(create_user("event-api-provider-identity"))

    create_response = client.post(
        EVENTS_URL,
        data=event_payload(source="google", external_id="forged-event"),
        content_type="application/json",
    )
    created = create_event(client)
    update_response = client.patch(
        f"{EVENTS_URL}{created['id']}/?expected_version=1",
        data={"source": "google", "external_id": "forged-event"},
        content_type="application/json",
    )

    assert create_response.status_code == 400
    assert update_response.status_code == 400
    event = CalendarEvent.objects.get(pk=created["id"])
    assert event.source == "local"
    assert event.external_id == ""


def test_event_api_stores_utc_values() -> None:
    client = authenticated_client(create_user())
    created = create_event(client)

    event = CalendarEvent.objects.get(pk=created["id"])
    assert event.start_at == datetime(2026, 7, 20, 1, tzinfo=UTC)

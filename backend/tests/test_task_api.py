from datetime import UTC, datetime
from typing import Any, cast

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import Client

from apps.tasks.models import Task, TaskStatus

pytestmark = pytest.mark.django_db

TASKS_URL = "/api/v1/tasks/"


def create_user(username: str = "task-api-user") -> User:
    return get_user_model().objects.create_user(username=username)


def task_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Prepare report",
        "due_at": "2026-07-20T18:00:00+08:00",
        "tags": ["work"],
    }
    payload.update(changes)
    return payload


def authenticated_client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def create_task(client: Client, **changes: object) -> dict[str, Any]:
    response = client.post(TASKS_URL, data=task_payload(**changes), content_type="application/json")
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


@pytest.mark.parametrize("method", ["get", "post"])
def test_task_collection_requires_authentication(method: str) -> None:
    response = getattr(Client(), method)(TASKS_URL)

    assert response.status_code in (401, 403)


def test_task_create_list_and_retrieve_are_user_scoped() -> None:
    user = create_user()
    other = create_user("task-api-other")
    client = authenticated_client(user)
    other_client = authenticated_client(other)
    created = create_task(client)
    create_task(other_client, title="Other task")

    list_response = client.get(
        TASKS_URL,
        {
            "status": TaskStatus.PENDING,
            "due_before": "2026-07-20T19:00:00+08:00",
        },
    )
    detail_response = client.get(f"{TASKS_URL}{created['id']}/")
    hidden_response = other_client.get(f"{TASKS_URL}{created['id']}/")

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]
    assert detail_response.status_code == 200
    assert detail_response.json()["due_at"] == "2026-07-20T10:00:00Z"
    assert hidden_response.status_code == 404


def test_task_patch_updates_fields_and_reschedules_atomically() -> None:
    client = authenticated_client(create_user())
    created = create_task(client)
    detail_url = f"{TASKS_URL}{created['id']}/"

    response = client.patch(
        detail_url,
        data={
            "title": "Updated report",
            "planned_start_at": "2026-07-20T09:00:00+08:00",
            "planned_end_at": "2026-07-20T10:00:00+08:00",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    task = Task.objects.get(pk=created["id"])
    assert task.title == "Updated report"
    assert task.planned_start_at == datetime(2026, 7, 20, 1, tzinfo=UTC)


def test_task_patch_rolls_back_other_changes_when_schedule_is_invalid() -> None:
    client = authenticated_client(create_user())
    created = create_task(client)

    response = client.patch(
        f"{TASKS_URL}{created['id']}/",
        data={
            "title": "Must roll back",
            "planned_start_at": "2026-07-20T10:00:00+08:00",
            "planned_end_at": "2026-07-20T09:00:00+08:00",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    task = Task.objects.get(pk=created["id"])
    assert task.title == "Prepare report"
    assert task.planned_start_at is None


def test_task_complete_endpoint_is_idempotent() -> None:
    client = authenticated_client(create_user())
    created = create_task(client)
    complete_url = f"{TASKS_URL}{created['id']}/complete/"

    response = client.post(complete_url)
    repeated_response = client.post(complete_url)

    assert response.status_code == 200
    assert response.json()["status"] == TaskStatus.COMPLETED
    assert response.json()["completed_at"] is not None
    assert repeated_response.status_code == 200
    assert repeated_response.json()["completed_at"] == response.json()["completed_at"]


def test_task_complete_endpoint_is_user_scoped() -> None:
    owner_client = authenticated_client(create_user())
    other_client = authenticated_client(create_user("task-complete-other"))
    created = create_task(owner_client)

    response = other_client.post(f"{TASKS_URL}{created['id']}/complete/")

    assert response.status_code == 404


def test_task_api_rejects_state_bypass_unknown_fields_and_naive_times() -> None:
    client = authenticated_client(create_user())
    created = create_task(client)
    detail_url = f"{TASKS_URL}{created['id']}/"

    state_response = client.patch(
        detail_url,
        data={"status": TaskStatus.COMPLETED},
        content_type="application/json",
    )
    user_response = client.post(
        TASKS_URL,
        data=task_payload(user=999),
        content_type="application/json",
    )
    naive_response = client.post(
        TASKS_URL,
        data=task_payload(due_at="2026-07-20T18:00:00"),
        content_type="application/json",
    )

    assert state_response.status_code == 400
    assert "status" in state_response.json()
    assert user_response.status_code == 400
    assert "user" in user_response.json()
    assert naive_response.status_code == 400


def test_task_api_rejects_cross_user_parent_reference() -> None:
    owner_client = authenticated_client(create_user())
    other_client = authenticated_client(create_user("task-parent-other"))
    parent = create_task(owner_client, title="Private parent")

    response = other_client.post(
        TASKS_URL,
        data=task_payload(parent_task=parent["id"]),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "parent_task" in response.json()

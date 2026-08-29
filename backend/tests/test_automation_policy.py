import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.planning.models import AutomationPolicy
from apps.tasks.services import CreateTaskCommand, TaskService

pytestmark = pytest.mark.django_db


def test_automation_policy_requires_explicit_reschedule_consent() -> None:
    user = User.objects.create_user("policy")
    client = Client()
    client.force_login(user)
    response = client.post(
        "/api/v1/planning/automation-policies/",
        data={
            "name": "Flexible tasks",
            "enabled": True,
            "allow_task_reschedule": False,
            "max_moves_per_run": 1,
            "requires_approval": True,
        },
        content_type="application/json",
    )
    assert response.status_code == 400
    assert AutomationPolicy.objects.filter(user=user).count() == 0


def test_automation_policy_can_be_paused_and_updated_by_owner() -> None:
    user = User.objects.create_user("policy-owner")
    policy = AutomationPolicy.objects.create(
        user=user,
        name="Flexible tasks",
        enabled=True,
        allow_task_reschedule=True,
        max_moves_per_run=3,
        requires_approval=False,
    )
    client = Client()
    client.force_login(user)

    response = client.patch(
        f"/api/v1/planning/automation-policies/{policy.pk}/",
        data={"enabled": False, "max_moves_per_run": 2},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["max_moves_per_run"] == 2
    policy.refresh_from_db()
    assert policy.enabled is False


def test_automation_policy_rejects_foreign_task_allowlist() -> None:
    user = User.objects.create_user("policy-scope-owner")
    other = User.objects.create_user("policy-scope-other")
    foreign_task = TaskService.create_task(
        CreateTaskCommand(user=other, title="Foreign task")
    )
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/v1/planning/automation-policies/",
        data={
            "name": "Scoped policy",
            "enabled": True,
            "allow_task_reschedule": True,
            "max_moves_per_run": 1,
            "requires_approval": False,
            "authorized_task_ids": [str(foreign_task.pk)],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not AutomationPolicy.objects.filter(user=user).exists()

from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from langchain_core.tools import StructuredTool

from apps.agents.context import RuntimeContext
from apps.agents.tools.planning_tools import request_plan_interaction
from apps.events.services import CreateEventCommand, EventService
from apps.interactions.models import (
    InteractionArtifact,
    InteractionStatus,
    InteractionSubmission,
    InteractionTelemetryEvent,
    InteractionType,
)
from apps.interactions.serializers import InteractionTelemetrySerializer
from apps.interactions.services import (
    InteractionArtifactService,
    InteractionConflictError,
)
from apps.planning.models import SchedulePlan
from apps.planning.services import PlanningService
from apps.preferences.services import UserPreferenceService
from apps.tasks.models import Task, TaskStatus
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.models import ScheduleChange

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)
PLAN_START = datetime(2026, 10, 5, 9, tzinfo=UTC)


def _make_user(username: str) -> User:
    user = get_user_model().objects.create_user(username=username)
    UserPreferenceService.update_for_user(
        user,
        {"timezone": "UTC", "workday_start": time(9), "workday_end": time(17)},
    )
    return user


def _make_plan(user: User, task_titles: tuple[str, ...]) -> tuple[list[Task], SchedulePlan]:
    tasks = [
        TaskService.create_task(CreateTaskCommand(user=user, title=title, estimated_minutes=60))
        for title in task_titles
    ]
    plan = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk for task in tasks],
        range_start=PLAN_START,
        range_end=datetime(2026, 10, 5, 17, tzinfo=UTC),
        strategy="plan_tasks_only",
        now=NOW,
    )
    return tasks, plan


def test_plan_local_priority_order_does_not_change_permanent_task_priority() -> None:
    user = _make_user("interaction-ranking")
    tasks, plan = _make_plan(user, ("Write paper", "Review Redis"))
    original_priorities = {task.pk: task.priority for task in tasks}
    interaction = InteractionArtifactService.ensure(
        user=user,
        interaction_type=InteractionType.PRIORITY_RANKING,
        plan_id=plan.pk,
        now=NOW,
    )

    result = InteractionArtifactService.submit(
        user=user,
        interaction_id=interaction.pk,
        expected_version=interaction.version,
        action="reorder",
        values={"ordered_task_ids": [str(task.pk) for task in reversed(tasks)]},
        idempotency_key="rank-plan-local-001",
        now=NOW,
    )

    assert result.accepted is True
    assert result.plan is not None
    assert result.plan.version == plan.version + 1
    assert {
        task.pk: task.priority for task in Task.objects.filter(pk__in=[task.pk for task in tasks])
    } == original_priorities
    plan_order = {
        item["task_id"]: item["planning_order"] for item in result.plan.items if item.get("task_id")
    }
    assert plan_order == {str(tasks[1].pk): 0, str(tasks[0].pk): 1}
    applied = PlanningService.apply_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=result.plan.version,
        now=NOW,
    )
    interaction.refresh_from_db()
    assert applied.status == "applied"


def test_agent_requests_typed_plan_interaction_through_application_service() -> None:
    user = _make_user("interaction-agent-request")
    _, plan = _make_plan(user, ("Write paper", "Review Redis"))
    runtime = SimpleNamespace(
        context=RuntimeContext(
            user_id=str(user.pk),
            request_id=str(uuid4()),
            timezone="UTC",
            locale="en",
            current_datetime=NOW,
            trigger_type="user_message",
            actor=user,
        )
    )

    request_plan_tool = cast(StructuredTool, request_plan_interaction)
    assert request_plan_tool.func is not None
    result = request_plan_tool.func(
        plan_id=plan.pk,
        interaction_type="priority_ranking",
        runtime=runtime,
    )

    artifact = InteractionArtifact.objects.get(pk=result["interaction_id"])
    assert artifact.plan_id == plan.pk
    assert artifact.plan_version == plan.version
    assert artifact.type == InteractionType.PRIORITY_RANKING
    assert artifact.allowed_actions == ["reorder", "dismiss"]
    assert result["status"] == InteractionStatus.PENDING


def test_plan_edit_marks_sibling_interaction_stale_and_requires_a_fresh_artifact() -> None:
    user = _make_user("interaction-stale-sibling")
    tasks, plan = _make_plan(user, ("Write paper", "Review Redis"))
    ranking = InteractionArtifactService.ensure(
        user=user,
        interaction_type=InteractionType.PRIORITY_RANKING,
        plan_id=plan.pk,
        now=NOW,
    )
    timeline = InteractionArtifactService.ensure(
        user=user,
        interaction_type=InteractionType.PLAN_TIMELINE_EDIT,
        plan_id=plan.pk,
        now=NOW,
    )

    result = InteractionArtifactService.submit(
        user=user,
        interaction_id=ranking.pk,
        expected_version=ranking.version,
        action="reorder",
        values={"ordered_task_ids": [str(task.pk) for task in reversed(tasks)]},
        idempotency_key="rank-stales-timeline-001",
        now=NOW,
    )

    timeline.refresh_from_db()
    assert result.accepted is True
    assert result.plan is not None
    updated_plan = result.plan
    assert timeline.status == InteractionStatus.STALE
    assert timeline.plan_version == plan.version
    with pytest.raises(InteractionConflictError, match="no longer pending"):
        InteractionArtifactService.submit(
            user=user,
            interaction_id=timeline.pk,
            expected_version=timeline.version,
            action="edit",
            values={"items": []},
            idempotency_key="stale-timeline-submit-001",
            now=NOW,
        )

    refreshed = InteractionArtifactService.ensure(
        user=user,
        interaction_type=InteractionType.PLAN_TIMELINE_EDIT,
        plan_id=plan.pk,
        now=NOW,
    )
    assert refreshed.pk != timeline.pk
    assert refreshed.status == InteractionStatus.PENDING
    assert refreshed.plan_version == updated_plan.version


def test_rejected_timeline_edit_returns_authoritative_conflict_and_candidate() -> None:
    user = _make_user("interaction-invalid-time")
    (task,), plan = _make_plan(user, ("Write paper",))
    original = next(item for item in plan.items if item.get("task_id") == str(task.pk))
    conflict_start = datetime(2026, 10, 5, 11, tzinfo=UTC)
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Project meeting",
            start_at=conflict_start,
            end_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
            timezone="UTC",
        )
    )
    interaction = InteractionArtifactService.ensure(
        user=user,
        interaction_type=InteractionType.PLAN_TIMELINE_EDIT,
        plan_id=plan.pk,
        now=NOW,
    )

    result = InteractionArtifactService.submit(
        user=user,
        interaction_id=interaction.pk,
        expected_version=interaction.version,
        action="edit",
        values={
            "items": [
                {
                    "task_id": str(task.pk),
                    "start_at": conflict_start.isoformat(),
                    "end_at": datetime(2026, 10, 5, 12, tzinfo=UTC).isoformat(),
                }
            ]
        },
        idempotency_key="timeline-conflict-001",
        now=NOW,
    )

    assert result.accepted is False
    assert "schedule_conflict" in result.reason_codes
    assert result.conflicts == (
        {
            "kind": "event",
            "label": "Project meeting",
            "start_at": conflict_start.isoformat(),
            "end_at": datetime(2026, 10, 5, 12, tzinfo=UTC).isoformat(),
        },
    )
    assert result.candidate is not None
    assert result.candidate["start_at"] != conflict_start.isoformat()
    assert result.plan is not None
    kept = next(item for item in result.plan.items if item.get("task_id") == str(task.pk))
    assert kept["start_at"] == original["start_at"]


def test_recovery_reports_conflicts_inside_the_edited_task_buffer() -> None:
    user = _make_user("interaction-buffer-conflict")
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Write paper",
            estimated_minutes=60,
            buffer_before_minutes=15,
        )
    )
    plan = PlanningService.propose_schedule_plan(
        user=user,
        task_ids=[task.pk],
        range_start=PLAN_START,
        range_end=datetime(2026, 10, 5, 17, tzinfo=UTC),
        strategy="plan_tasks_only",
        now=NOW,
    )
    original = next(item for item in plan.items if item.get("task_id") == str(task.pk))
    original_start = datetime.fromisoformat(original["start_at"])
    original_end = datetime.fromisoformat(original["end_at"])
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Buffer meeting",
            start_at=original_start - timedelta(minutes=10),
            end_at=original_start,
            timezone="UTC",
        )
    )
    interaction = InteractionArtifactService.ensure(
        user=user,
        interaction_type=InteractionType.PLAN_TIMELINE_EDIT,
        plan_id=plan.pk,
        now=NOW,
    )

    result = InteractionArtifactService.submit(
        user=user,
        interaction_id=interaction.pk,
        expected_version=interaction.version,
        action="edit",
        values={
            "items": [
                {
                    "task_id": str(task.pk),
                    "start_at": original["start_at"],
                    "end_at": original["end_at"],
                }
            ]
        },
        idempotency_key="timeline-buffer-conflict-001",
        now=NOW,
    )

    assert result.accepted is False
    assert "schedule_conflict" in result.reason_codes
    assert result.conflicts == (
        {
            "kind": "event",
            "label": "Buffer meeting",
            "start_at": (original_start - timedelta(minutes=10)).isoformat(),
            "end_at": original_start.isoformat(),
        },
    )
    assert result.candidate is not None
    assert datetime.fromisoformat(result.candidate["end_at"]) > original_end


def test_plan_edit_idempotency_replay_returns_current_plan() -> None:
    user = _make_user("interaction-replay")
    tasks, plan = _make_plan(user, ("Write paper", "Review Redis"))
    interaction = InteractionArtifactService.ensure(
        user=user,
        interaction_type=InteractionType.PRIORITY_RANKING,
        plan_id=plan.pk,
        now=NOW,
    )
    ordered_task_ids = [str(task.pk) for task in tasks]
    first = InteractionArtifactService.submit(
        user=user,
        interaction_id=interaction.pk,
        expected_version=interaction.version,
        action="reorder",
        values={"ordered_task_ids": ordered_task_ids},
        idempotency_key="rank-replay-001",
        now=NOW,
    )
    replay = InteractionArtifactService.submit(
        user=user,
        interaction_id=interaction.pk,
        expected_version=interaction.version,
        action="reorder",
        values={"ordered_task_ids": ordered_task_ids},
        idempotency_key="rank-replay-001",
        now=NOW,
    )

    assert first.accepted is True
    assert replay.replayed is True
    assert first.plan is not None
    assert replay.plan is not None
    first_plan = first.plan
    replay_plan = replay.plan
    assert replay_plan.version == first_plan.version
    assert (
        InteractionSubmission.objects.filter(user=user, idempotency_key="rank-replay-001").count()
        == 1
    )


def test_resized_estimate_stays_in_draft_until_apply_then_updates_task_service() -> None:
    user = _make_user("interaction-resize-apply")
    (task,), plan = _make_plan(user, ("Write paper",))
    interaction = InteractionArtifactService.ensure(
        user=user,
        interaction_type=InteractionType.PLAN_TIMELINE_EDIT,
        plan_id=plan.pk,
        now=NOW,
    )

    result = InteractionArtifactService.submit(
        user=user,
        interaction_id=interaction.pk,
        expected_version=interaction.version,
        action="edit",
        values={
            "items": [
                {
                    "task_id": str(task.pk),
                    "start_at": "2026-10-05T09:00:00+00:00",
                    "end_at": "2026-10-05T10:30:00+00:00",
                }
            ]
        },
        idempotency_key="timeline-resize-001",
        now=NOW,
    )
    task.refresh_from_db()
    assert result.accepted is True
    assert result.plan is not None
    assert task.estimated_minutes == 60

    PlanningService.apply_schedule_plan(
        user=user,
        plan_id=plan.pk,
        expected_version=result.plan.version,
        now=NOW,
    )

    task.refresh_from_db()
    assert task.estimated_minutes == 90
    assert task.planned_start_at == datetime(2026, 10, 5, 9, tzinfo=UTC)
    assert task.planned_end_at == datetime(2026, 10, 5, 10, 30, tzinfo=UTC)
    change = ScheduleChange.objects.filter(
        entity_id=task.pk,
        entity_type="task",
        operation="updated",
    ).latest("created_at")
    assert change.old_snapshot["estimated_minutes"] == 60
    assert change.new_snapshot["estimated_minutes"] == 90


def test_completion_feedback_is_optional_structured_and_does_not_recomplete_task() -> None:
    user = _make_user("interaction-completion")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Write paper", estimated_minutes=60)
    )
    completed = TaskService.complete_task(task_id=task.pk, user=user, occurred_at=NOW)
    assert (
        InteractionArtifact.objects.filter(
            user=user,
            task=task,
            type=InteractionType.TASK_COMPLETION,
            status=InteractionStatus.PENDING,
        ).count()
        == 1
    )
    interaction = InteractionArtifactService.ensure(
        user=user,
        interaction_type=InteractionType.TASK_COMPLETION,
        task_id=task.pk,
        now=NOW,
    )

    result = InteractionArtifactService.submit(
        user=user,
        interaction_id=interaction.pk,
        expected_version=interaction.version,
        action="submit_feedback",
        values={"rating": "longer", "reason": "more_complex"},
        idempotency_key="completion-feedback-001",
        now=NOW,
    )

    completed.refresh_from_db()
    assert result.accepted is True
    assert completed.status == TaskStatus.COMPLETED
    assert completed.completed_at == NOW
    assert result.interaction.payload["completion_feedback"] == {
        "rating": "longer",
        "reason": "more_complex",
    }
    assert (
        InteractionTelemetryEvent.objects.filter(
            event_type="completion_feedback_rate",
            interaction_type=InteractionType.TASK_COMPLETION,
        ).count()
        == 1
    )
    assert (
        InteractionTelemetryEvent.objects.filter(
            event_type="interaction_completed",
            interaction_type=InteractionType.TASK_COMPLETION,
        ).count()
        == 1
    )

    with pytest.raises(ValueError, match="rating must be"):
        InteractionArtifactService.submit(
            user=user,
            interaction_id=interaction.pk,
            expected_version=result.interaction.version,
            action="submit_feedback",
            values={"rating": "maybe"},
            idempotency_key="completion-feedback-invalid",
            now=NOW,
        )


def test_task_completion_succeeds_and_retries_optional_feedback_creation() -> None:
    user = _make_user("interaction-completion-retry")
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Write paper", estimated_minutes=60)
    )

    with patch(
        "apps.interactions.services.InteractionArtifactService.ensure",
        side_effect=RuntimeError("interaction store temporarily unavailable"),
    ):
        completed = TaskService.complete_task(task_id=task.pk, user=user, occurred_at=NOW)

    assert completed.status == TaskStatus.COMPLETED
    assert not InteractionArtifact.objects.filter(task=task).exists()

    completed = TaskService.complete_task(task_id=task.pk, user=user, occurred_at=NOW)
    assert completed.status == TaskStatus.COMPLETED
    assert (
        InteractionArtifact.objects.filter(
            user=user,
            task=task,
            type=InteractionType.TASK_COMPLETION,
            status=InteractionStatus.PENDING,
        ).count()
        == 1
    )


def test_interaction_telemetry_is_anonymous_and_excludes_content_fields() -> None:
    event = InteractionTelemetryEvent.objects.create(
        event_type="interaction_shown",
        interaction_type="task_completion",
    )

    assert not hasattr(event, "user_id")
    assert not hasattr(event, "task_id")
    assert not hasattr(event, "conversation_id")


@pytest.mark.parametrize(
    "event_type",
    (
        "interaction_completed",
        "interaction_abandoned",
        "completion_feedback_rate",
        "plan_acceptance_after_interaction",
        "memory_suggestion_accepted",
        "day_close_completion_rate",
    ),
)
def test_clients_cannot_submit_server_owned_telemetry_outcomes(event_type: str) -> None:
    serializer = InteractionTelemetrySerializer(
        data={"event_type": event_type, "interaction_type": "task_completion"}
    )

    assert serializer.is_valid() is False
    assert "event_type" in serializer.errors


@pytest.mark.parametrize(
    ("event_type", "metric_field"),
    (
        ("interaction_shown", "actual_vs_planned_ratio"),
        ("interaction_started", "duration_ms"),
        ("plan_edit", "undo_count"),
        ("undo", "plan_edit_count"),
    ),
)
def test_client_telemetry_rejects_metrics_not_meaningful_for_event(
    event_type: str, metric_field: str
) -> None:
    serializer = InteractionTelemetrySerializer(
        data={
            "event_type": event_type,
            "interaction_type": "plan_timeline_edit",
            metric_field: 1,
        }
    )

    assert serializer.is_valid() is False
    assert metric_field in serializer.errors

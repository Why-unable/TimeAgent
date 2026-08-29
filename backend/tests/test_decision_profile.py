from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import Client
from langgraph.store.memory import InMemoryStore

from apps.tasks.execution_services import RecordExecutionSignalCommand, TaskExecutionSignalService
from apps.tasks.models import TaskExecutionSignalType
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.decision_profile import (
    DURATION_CATEGORY,
    DecisionProfileService,
    RecordDecisionFeedbackCommand,
)
from apps.time_memory.models import TimeDecisionFeedbackAction
from apps.time_memory.schemas import BehaviorWindow, ExecutionCalibration, TimeMemoryProfile

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 24, 1, 0, tzinfo=UTC)


def create_user(username: str = "decision-profile-user") -> User:
    return get_user_model().objects.create_user(username=username)


def create_executed_task(
    *,
    user: User,
    key: str,
    title: str,
    started_at: datetime,
    actual_minutes: int,
    estimated_minutes: int = 30,
    project: str = "",
) -> None:
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title=title,
            project=project,
            estimated_minutes=estimated_minutes,
        )
    )
    TaskExecutionSignalService.record(
        RecordExecutionSignalCommand(
            user=user,
            task_id=task.pk,
            signal_type=TaskExecutionSignalType.STARTED,
            occurred_at=started_at,
            idempotency_key=f"{key}-start",
        )
    )
    TaskExecutionSignalService.record(
        RecordExecutionSignalCommand(
            user=user,
            task_id=task.pk,
            signal_type=TaskExecutionSignalType.COMPLETED,
            occurred_at=started_at + timedelta(minutes=actual_minutes),
            idempotency_key=f"{key}-complete",
        )
    )


def test_decision_profile_uses_execution_calibration_and_is_explainable() -> None:
    user = create_user()
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="Calibrated task", estimated_minutes=30)
    )
    TaskExecutionSignalService.record(
        RecordExecutionSignalCommand(
            user=user,
            task_id=task.pk,
            signal_type=TaskExecutionSignalType.STARTED,
            occurred_at=NOW,
            idempotency_key="profile-start",
        )
    )
    TaskExecutionSignalService.record(
        RecordExecutionSignalCommand(
            user=user,
            task_id=task.pk,
            signal_type=TaskExecutionSignalType.COMPLETED,
            occurred_at=NOW + timedelta(minutes=45),
            idempotency_key="profile-complete",
        )
    )
    store = InMemoryStore()
    memory_profile = TimeMemoryProfile(
        user_id=str(user.pk),
        generated_at=NOW,
        data_until=NOW,
        timezone="Asia/Shanghai",
        behavior_windows={
            "30d": BehaviorWindow(
                window="30d",
                start_date=NOW.date() - timedelta(days=29),
                end_date=NOW.date(),
                sample_days=30,
                event_count=3,
                execution_calibration=ExecutionCalibration(
                    sample_count=1,
                    median_actual_to_estimated_ratio=1.5,
                    confidence=0.1,
                ),
            )
        },
        version=2,
    )
    with patch(
        "apps.time_memory.decision_profile.TimeMemoryRepository.get",
        return_value=memory_profile,
    ):
        profile = DecisionProfileService.get(user=user, store=store)
    assert profile.category == DURATION_CATEGORY
    assert profile.duration_multiplier == 1.5
    assert profile.sample_count == 1
    assert profile.source == "execution_calibration"
    assert profile.evidence


def test_decision_profile_feedback_is_idempotent_and_can_disable() -> None:
    user = create_user("decision-profile-feedback")
    command = RecordDecisionFeedbackCommand(
        user=user,
        category=DURATION_CATEGORY,
        action=TimeDecisionFeedbackAction.DISABLE,
        value={},
        idempotency_key="disable-duration",
        source="android",
    )
    first = DecisionProfileService.record_feedback(command)
    repeated = DecisionProfileService.record_feedback(command)
    assert first.pk == repeated.pk
    store = InMemoryStore()
    with patch("apps.time_memory.decision_profile.TimeMemoryRepository.get", return_value=None):
        profile = DecisionProfileService.get(user=user, store=store)
    assert profile.enabled is False
    assert profile.source == "user_disabled"


def test_decision_profile_api_is_user_scoped_and_validates_feedback() -> None:
    user = create_user("decision-profile-api")
    client = Client()
    client.force_login(user)

    @contextmanager
    def fake_store() -> Iterator[InMemoryStore]:
        yield InMemoryStore()

    with patch("apps.time_memory.views.open_postgres_store", fake_store):
        response = client.get("/api/v1/time-memory/me/decision-profile/")
    feedback = client.post(
        "/api/v1/time-memory/me/decision-profile/",
        data={
            "category": DURATION_CATEGORY,
            "action": "override",
            "value": {"duration_multiplier": 1.25},
            "idempotency_key": "api-feedback-1",
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["source"] == "global_default"
    assert feedback.status_code == 201


def test_duration_recommendation_uses_explicit_project_and_reports_fallback() -> None:
    user = create_user("duration-recommendation")
    start = NOW - timedelta(days=10)
    for index in range(3):
        historical = TaskService.create_task(
            CreateTaskCommand(
                user=user,
                title=f"Historical {index}",
                project="Research",
                estimated_minutes=30,
            )
        )
        TaskExecutionSignalService.record(
            RecordExecutionSignalCommand(
                user=user,
                task_id=historical.pk,
                signal_type=TaskExecutionSignalType.STARTED,
                occurred_at=start + timedelta(days=index),
                idempotency_key=f"rec-start-{index}",
            )
        )
        TaskExecutionSignalService.record(
            RecordExecutionSignalCommand(
                user=user,
                task_id=historical.pk,
                signal_type=TaskExecutionSignalType.COMPLETED,
                occurred_at=start + timedelta(days=index, minutes=45),
                idempotency_key=f"rec-done-{index}",
            )
        )
    target = TaskService.create_task(
        CreateTaskCommand(
            user=user, title="Next research", project="Research", estimated_minutes=40
        )
    )
    store = InMemoryStore()
    with patch("apps.time_memory.decision_profile.TimeMemoryRepository.get", return_value=None):
        recommendation = DecisionProfileService.recommend_duration(
            user=user, store=store, task_id=target.pk, now=NOW
        )
    assert recommendation.segment == "project:research"
    assert recommendation.source == "explicit_segment_execution_calibration"
    assert recommendation.recommended_minutes == 60
    assert recommendation.fallback_reason is None


def test_task_feedback_adjusts_only_matching_explicit_segment() -> None:
    user = create_user("duration-segment-feedback")
    research = TaskService.create_task(
        CreateTaskCommand(user=user, title="Research", project="Research", estimated_minutes=40)
    )
    admin = TaskService.create_task(
        CreateTaskCommand(user=user, title="Admin", project="Admin", estimated_minutes=40)
    )
    DecisionProfileService.record_feedback(
        RecordDecisionFeedbackCommand(
            user=user,
            category=DURATION_CATEGORY,
            action=TimeDecisionFeedbackAction.TOO_SHORT,
            value={"segment": "project:research", "task_id": str(research.pk)},
            idempotency_key="research-too-short",
        )
    )
    store = InMemoryStore()
    with patch("apps.time_memory.decision_profile.TimeMemoryRepository.get", return_value=None):
        research_result = DecisionProfileService.recommend_duration(
            user=user, store=store, task_id=research.pk, now=NOW
        )
        admin_result = DecisionProfileService.recommend_duration(
            user=user, store=store, task_id=admin.pk, now=NOW
        )
    assert research_result.recommended_minutes == 50
    assert research_result.source == "user_segment_feedback"
    assert admin_result.recommended_minutes == 40


def test_accept_feedback_does_not_shadow_global_override() -> None:
    user = create_user("duration-feedback-control")
    DecisionProfileService.record_feedback(
        RecordDecisionFeedbackCommand(
            user=user,
            category=DURATION_CATEGORY,
            action=TimeDecisionFeedbackAction.OVERRIDE,
            value={"duration_multiplier": 1.5},
            idempotency_key="global-override",
        )
    )
    DecisionProfileService.record_feedback(
        RecordDecisionFeedbackCommand(
            user=user,
            category=DURATION_CATEGORY,
            action=TimeDecisionFeedbackAction.ACCEPT,
            value={"segment": "project:research"},
            idempotency_key="segment-accept",
        )
    )
    with patch("apps.time_memory.decision_profile.TimeMemoryRepository.get", return_value=None):
        profile = DecisionProfileService.get(user=user, store=InMemoryStore())
    assert profile.source == "user_override"
    assert profile.duration_multiplier == 1.5


def test_duration_recommendation_uses_explainable_semantic_similarity_fallback() -> None:
    user = create_user("duration-semantic-fallback")
    for index in range(3):
        create_executed_task(
            user=user,
            key=f"semantic-{index}",
            title=f"Draft report section {index}",
            started_at=NOW - timedelta(days=10 - index),
            actual_minutes=60,
        )
    target = TaskService.create_task(
        CreateTaskCommand(user=user, title="Write project report", estimated_minutes=40)
    )

    with patch("apps.time_memory.decision_profile.TimeMemoryRepository.get", return_value=None):
        recommendation = DecisionProfileService.recommend_duration(
            user=user,
            store=InMemoryStore(),
            task_id=target.pk,
            now=NOW,
        )

    assert recommendation.segment == "semantic:writing"
    assert recommendation.source == "semantic_similarity_execution_calibration"
    assert recommendation.recommended_minutes == 80
    assert recommendation.sample_count == 3
    assert recommendation.classification.category == "writing"
    assert recommendation.classification.matched_signals
    assert recommendation.feature_version == "duration-recommendation-v2"
    assert recommendation.expires_at == (NOW + timedelta(days=7)).isoformat()


def test_duration_recommendation_weights_recent_execution_more_than_old_samples() -> None:
    user = create_user("duration-time-decay")
    for index in range(3):
        create_executed_task(
            user=user,
            key=f"old-{index}",
            title=f"Focus old {index}",
            project="Focus",
            started_at=NOW - timedelta(days=170 - index),
            actual_minutes=15,
        )
    for index in range(2):
        create_executed_task(
            user=user,
            key=f"recent-{index}",
            title=f"Focus recent {index}",
            project="Focus",
            started_at=NOW - timedelta(days=5 - index),
            actual_minutes=60,
        )
    target = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Next focus",
            project="Focus",
            estimated_minutes=30,
        )
    )

    with patch("apps.time_memory.decision_profile.TimeMemoryRepository.get", return_value=None):
        recommendation = DecisionProfileService.recommend_duration(
            user=user,
            store=InMemoryStore(),
            task_id=target.pk,
            now=NOW,
        )

    assert recommendation.duration_multiplier == 2.0
    assert recommendation.recommended_minutes == 60
    assert recommendation.decay_half_life_days == 60


def test_segment_disable_does_not_disable_the_global_duration_profile() -> None:
    user = create_user("duration-segment-disable")
    research = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Research task",
            project="Research",
            estimated_minutes=40,
        )
    )
    admin = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Admin task",
            project="Admin",
            estimated_minutes=40,
        )
    )
    DecisionProfileService.record_feedback(
        RecordDecisionFeedbackCommand(
            user=user,
            category=DURATION_CATEGORY,
            action=TimeDecisionFeedbackAction.DISABLE,
            value={"segment": "project:research", "task_id": str(research.pk)},
            idempotency_key="disable-research-segment",
        )
    )

    with patch("apps.time_memory.decision_profile.TimeMemoryRepository.get", return_value=None):
        profile = DecisionProfileService.get(user=user, store=InMemoryStore())
        research_recommendation = DecisionProfileService.recommend_duration(
            user=user,
            store=InMemoryStore(),
            task_id=research.pk,
            now=NOW,
        )
        admin_recommendation = DecisionProfileService.recommend_duration(
            user=user,
            store=InMemoryStore(),
            task_id=admin.pk,
            now=NOW,
        )

    assert profile.enabled is True
    assert research_recommendation.source == "user_disabled_segment"
    assert research_recommendation.fallback_reason == "duration_segment_disabled"
    assert admin_recommendation.source != "user_disabled_segment"

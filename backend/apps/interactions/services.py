from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.interactions.models import (
    InteractionArtifact,
    InteractionStatus,
    InteractionSubmission,
    InteractionTelemetryEvent,
    InteractionTelemetryEventType,
    InteractionType,
)
from apps.planning.models import SchedulePlan, SchedulePlanStatus
from apps.planning.services import PlanningService
from apps.tasks.models import Task, TaskStatus
from apps.time_memory.decision_profile import (
    DURATION_CATEGORY,
    DecisionProfileService,
    RecordDecisionFeedbackCommand,
)
from apps.time_memory.models import TimeDecisionFeedbackAction
from common.database_locks import lock_user_schedule_writes


class InteractionConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class InteractionSubmitResult:
    interaction: InteractionArtifact
    accepted: bool
    plan: SchedulePlan | None
    detail: str | None = None
    reason_codes: tuple[str, ...] = ()
    conflicts: tuple[dict[str, str], ...] = ()
    candidate: dict[str, str] | None = None
    replayed: bool = False


class InteractionArtifactService:
    """Application boundary for durable, allowlisted interaction decisions."""

    ACTIONS = {
        InteractionType.PRIORITY_RANKING: ("reorder", "dismiss"),
        InteractionType.PLAN_TIMELINE_EDIT: ("edit", "dismiss"),
        InteractionType.TASK_COMPLETION: (
            "submit_feedback",
            "dismiss",
        ),
        InteractionType.MEMORY_SUGGESTION: ("accept", "dismiss"),
    }

    @staticmethod
    @transaction.atomic
    def ensure(
        *,
        user: User,
        interaction_type: str,
        plan_id: UUID | None = None,
        task_id: UUID | None = None,
        conversation_id: UUID | None = None,
        agent_run_id: UUID | None = None,
        now: datetime | None = None,
    ) -> InteractionArtifact:
        anchor = now or timezone.now()
        try:
            artifact_type = InteractionType(interaction_type)
        except ValueError as exc:
            raise ValueError("Unsupported interaction type") from exc
        if artifact_type in {
            InteractionType.PRIORITY_RANKING,
            InteractionType.PLAN_TIMELINE_EDIT,
        }:
            if plan_id is None or task_id is not None:
                raise ValueError("Plan interactions require plan_id only")
            plan = SchedulePlan.objects.get(pk=plan_id, user=user)
            if plan.status != SchedulePlanStatus.DRAFT or plan.expires_at <= anchor:
                raise ValueError("Only an active draft plan can have an interaction")
            task = None
            expires_at = plan.expires_at
            payload: dict[str, Any] = {"plan_id": str(plan.pk)}
        else:
            if task_id is None or plan_id is not None:
                raise ValueError("Task completion interactions require task_id only")
            task = Task.objects.get(pk=task_id, user=user)
            if task.status != TaskStatus.COMPLETED:
                raise ValueError("Task completion feedback is available after completion")
            plan = None
            expires_at = min(anchor + timedelta(days=14), task.completed_at + timedelta(days=14))
            payload = {"task_id": str(task.pk)}
        conversation = None
        if conversation_id is not None:
            from apps.conversations.models import Conversation

            conversation = Conversation.objects.get(pk=conversation_id, user=user)
        run = None
        if agent_run_id is not None:
            from apps.conversations.models import AgentRun

            run = AgentRun.objects.select_related("conversation").get(
                pk=agent_run_id, conversation__user=user
            )
            if conversation is not None and run.conversation_id != conversation.pk:
                raise ValueError("Agent run must belong to the supplied conversation")
            conversation = conversation or run.conversation

        latest = (
            InteractionArtifact.objects.select_for_update()
            .filter(
                user=user,
                type=artifact_type,
                plan=plan,
                task=task,
            )
            .order_by("-created_at")
            .first()
        )
        if latest is not None:
            if latest.status == InteractionStatus.PENDING and latest.expires_at > anchor:
                update_fields: set[str] = set()
                if plan is not None and latest.plan_version != plan.version:
                    latest.plan_version = plan.version
                    update_fields.add("plan_version")
                if conversation is not None and latest.conversation_id != conversation.pk:
                    latest.conversation = conversation
                    update_fields.add("conversation")
                if run is not None and latest.agent_run_id != run.pk:
                    latest.agent_run = run
                    update_fields.add("agent_run")
                if update_fields:
                    latest.save(update_fields=[*sorted(update_fields), "updated_at"])
                return latest
            if latest.status == InteractionStatus.PENDING:
                latest.status = InteractionStatus.EXPIRED
                latest.resolved_at = anchor
                latest.save(update_fields=["status", "resolved_at", "updated_at"])
            if plan is None or latest.plan_version == plan.version:
                return latest
        artifact = InteractionArtifact(
            user=user,
            conversation=conversation,
            agent_run=run,
            plan=plan,
            plan_version=plan.version if plan is not None else None,
            task=task,
            type=artifact_type,
            payload=payload,
            allowed_actions=list(InteractionArtifactService.ACTIONS[artifact_type]),
            expires_at=expires_at,
        )
        artifact.full_clean()
        try:
            with transaction.atomic():
                artifact.save(force_insert=True)
        except IntegrityError:
            concurrent = (
                InteractionArtifact.objects.select_for_update()
                .filter(
                    user=user,
                    type=artifact_type,
                    plan=plan,
                    task=task,
                    status=InteractionStatus.PENDING,
                    expires_at__gt=anchor,
                )
                .order_by("-created_at")
                .first()
            )
            if concurrent is None:
                raise
            return concurrent
        return artifact

    @staticmethod
    def list_pending(
        *,
        user: User,
        plan_id: UUID | None = None,
        task_id: UUID | None = None,
        interaction_type: str | None = None,
        now: datetime | None = None,
    ) -> list[InteractionArtifact]:
        anchor = now or timezone.now()
        InteractionArtifact.objects.filter(
            user=user,
            status=InteractionStatus.PENDING,
            expires_at__lte=anchor,
        ).update(status=InteractionStatus.EXPIRED, resolved_at=anchor)
        rows = InteractionArtifact.objects.filter(
            user=user,
            status=InteractionStatus.PENDING,
            expires_at__gt=anchor,
        ).select_related("plan", "task", "conversation", "agent_run")
        if plan_id is not None:
            rows = rows.filter(plan_id=plan_id)
        if task_id is not None:
            rows = rows.filter(task_id=task_id)
        if interaction_type is not None:
            rows = rows.filter(type=interaction_type)
        return list(rows)

    @staticmethod
    @transaction.atomic
    def resolve_plan_interactions(
        *,
        user: User,
        plan_id: UUID,
        final_status: str,
        now: datetime | None = None,
    ) -> None:
        if final_status not in {InteractionStatus.COMPLETED, InteractionStatus.ABANDONED}:
            raise ValueError("Unsupported final plan interaction status")
        anchor = now or timezone.now()
        pending = list(
            InteractionArtifact.objects.select_for_update().filter(
                user=user,
                plan_id=plan_id,
                status=InteractionStatus.PENDING,
            )
        )
        if not pending:
            return
        touched_types = {row.type for row in pending if row.version > 1}
        InteractionArtifact.objects.filter(pk__in=[row.pk for row in pending]).update(
            status=final_status,
            resolved_at=anchor,
            updated_at=anchor,
        )
        if final_status != InteractionStatus.COMPLETED or not touched_types:
            return
        for interaction_type in sorted(touched_types):
            InteractionTelemetryEvent.objects.create(
                event_type=InteractionTelemetryEventType.PLAN_ACCEPTED,
                interaction_type=interaction_type,
            )

    @staticmethod
    @transaction.atomic
    def submit(
        *,
        user: User,
        interaction_id: UUID,
        expected_version: int,
        action: str,
        values: dict[str, Any],
        idempotency_key: str,
        now: datetime | None = None,
    ) -> InteractionSubmitResult:
        anchor = now or timezone.now()
        key = idempotency_key.strip()
        if not key:
            raise ValueError("idempotency_key cannot be blank")
        if not isinstance(values, dict):
            raise ValueError("values must be an object")
        replay = InteractionSubmission.objects.filter(user=user, idempotency_key=key).first()
        artifact_header = InteractionArtifact.objects.only("type", "plan_id").get(
            pk=interaction_id, user=user
        )
        if artifact_header.type in {
            InteractionType.PRIORITY_RANKING,
            InteractionType.PLAN_TIMELINE_EDIT,
        }:
            # Acquire the shared schedule lock before the artifact row. Apply takes
            # this same lock before its plan and interaction rows.
            lock_user_schedule_writes(user)
        artifact = (
            InteractionArtifact.objects.select_for_update(of=("self",))
            .select_related("plan", "task")
            .get(pk=interaction_id, user=user)
        )
        if replay is not None:
            if (
                replay.interaction_id != artifact.pk
                or replay.expected_version != expected_version
                or replay.action != action
                or replay.values != values
            ):
                raise InteractionConflictError("Idempotency key was reused for another decision")
            replay_plan = (
                SchedulePlan.objects.get(pk=artifact.plan_id, user=user)
                if artifact.plan_id is not None
                else None
            )
            return InteractionSubmitResult(
                interaction=artifact,
                accepted=bool(replay.result.get("accepted")),
                plan=replay_plan,
                detail=replay.result.get("detail"),
                reason_codes=tuple(replay.result.get("reason_codes", [])),
                conflicts=tuple(replay.result.get("conflicts", [])),
                candidate=replay.result.get("candidate"),
                replayed=True,
            )
        if artifact.status != InteractionStatus.PENDING:
            raise InteractionConflictError("Interaction is no longer pending")
        if artifact.expires_at <= anchor:
            artifact.status = InteractionStatus.EXPIRED
            artifact.resolved_at = anchor
            artifact.save(update_fields=["status", "resolved_at", "updated_at"])
            raise InteractionConflictError("Interaction has expired")
        if artifact.version != expected_version:
            raise InteractionConflictError("Interaction version conflict")
        if action not in artifact.allowed_actions:
            raise ValueError("Action is not allowed for this interaction")

        result: dict[str, Any] = {"accepted": True}
        plan: SchedulePlan | None = None
        reason_codes: tuple[str, ...] = ()
        conflicts: tuple[dict[str, str], ...] = ()
        candidate: dict[str, str] | None = None
        if artifact.type in {
            InteractionType.PRIORITY_RANKING,
            InteractionType.PLAN_TIMELINE_EDIT,
        }:
            if artifact.plan is None or artifact.plan_version is None:
                raise InteractionConflictError("Plan interaction is missing its plan version")
            if artifact.plan.version != artifact.plan_version:
                raise InteractionConflictError("Schedule plan version conflict")
            if action == "dismiss":
                if values:
                    raise ValueError("dismiss does not accept values")
                artifact.status = InteractionStatus.ABANDONED
                artifact.resolved_at = anchor
            else:
                edits: list[dict[str, Any]] = []
                ordered_task_ids: list[UUID] | None = None
                if action == "edit":
                    if set(values) != {"items"}:
                        raise ValueError("Timeline edit accepts only items")
                    edits = InteractionArtifactService._parse_plan_items(values)
                elif action == "reorder":
                    if set(values) != {"ordered_task_ids"}:
                        raise ValueError("Priority ranking accepts only ordered_task_ids")
                    raw_ids = values.get("ordered_task_ids")
                    if not isinstance(raw_ids, list) or not raw_ids:
                        raise ValueError("ordered_task_ids must be a non-empty list")
                    try:
                        ordered_task_ids = [UUID(str(task_id)) for task_id in raw_ids]
                    except (ValueError, TypeError) as exc:
                        raise ValueError("ordered_task_ids must contain task IDs") from exc
                try:
                    plan = PlanningService.edit_schedule_plan(
                        user=user,
                        plan_id=artifact.plan_id,
                        expected_version=artifact.plan_version,
                        edits=edits,
                        ordered_task_ids=ordered_task_ids,
                        now=anchor,
                    )
                except ValueError as exc:
                    reason_codes, candidate, conflict_rows = PlanningService.plan_edit_recovery(
                        user=user,
                        plan_id=artifact.plan_id,
                        edits=edits,
                        ordered_task_ids=ordered_task_ids,
                        now=anchor,
                    )
                    conflicts = tuple(conflict_rows)
                    result = {
                        "accepted": False,
                        "detail": str(exc),
                        "reason_codes": list(reason_codes),
                        "conflicts": list(conflicts),
                        "candidate": candidate,
                    }
                    plan = SchedulePlan.objects.get(pk=artifact.plan_id, user=user)
                    if artifact.plan_version != plan.version:
                        artifact.plan_version = plan.version
                        InteractionArtifact.objects.filter(
                            user=user,
                            plan=plan,
                            status=InteractionStatus.PENDING,
                        ).update(plan_version=plan.version)
            if result["accepted"]:
                artifact.version += 1
                if plan is not None:
                    artifact.plan_version = plan.version
                    InteractionArtifact.objects.filter(
                        user=user,
                        plan=plan,
                        status=InteractionStatus.PENDING,
                    ).exclude(pk=artifact.pk).update(plan_version=plan.version)
        elif artifact.type == InteractionType.TASK_COMPLETION:
            if artifact.task is None:
                raise InteractionConflictError("Completion interaction is missing its task")
            if action == "dismiss":
                if values:
                    raise ValueError("dismiss does not accept values")
                artifact.status = InteractionStatus.ABANDONED
                artifact.resolved_at = anchor
            elif action == "submit_feedback":
                InteractionArtifactService._validate_completion_feedback(values)
                artifact.payload = {**artifact.payload, "completion_feedback": values}
                artifact.version += 1
            else:
                raise ValueError("Unsupported completion feedback action")
        elif artifact.type == InteractionType.MEMORY_SUGGESTION:
            if artifact.task is None:
                raise InteractionConflictError("Memory suggestion is missing its task")
            if action == "dismiss":
                if values:
                    raise ValueError("dismiss does not accept values")
                artifact.status = InteractionStatus.ABANDONED
                artifact.resolved_at = anchor
            elif action == "accept":
                InteractionArtifactService._record_memory_suggestion(
                    user=user,
                    task=artifact.task,
                    values=values,
                    idempotency_key=key,
                )
                artifact.version += 1
                artifact.status = InteractionStatus.COMPLETED
                artifact.resolved_at = anchor
            else:
                raise ValueError("Unsupported memory suggestion action")
        artifact.save(
            update_fields=[
                "payload",
                "status",
                "resolved_at",
                "version",
                "plan_version",
                "updated_at",
            ]
        )
        submission = InteractionSubmission(
            interaction=artifact,
            user=user,
            expected_version=expected_version,
            action=action,
            values=values,
            result=result,
            idempotency_key=key,
        )
        submission.full_clean()
        try:
            submission.save(force_insert=True)
        except IntegrityError as exc:
            raise InteractionConflictError("Idempotency key was already used") from exc
        if result["accepted"]:
            if action == "dismiss":
                InteractionTelemetryService.record(
                    event_data={
                        "event_type": InteractionTelemetryEventType.ABANDONED,
                        "interaction_type": artifact.type,
                    }
                )
            else:
                InteractionTelemetryService.record(
                    event_data={
                        "event_type": InteractionTelemetryEventType.COMPLETED,
                        "interaction_type": artifact.type,
                    }
                )
                if artifact.type == InteractionType.TASK_COMPLETION and action == "submit_feedback":
                    from apps.tasks.execution_services import TaskExecutionSignalService

                    execution = TaskExecutionSignalService.summary(
                        user=user, task_id=artifact.task_id, now=anchor
                    )
                    actual_vs_planned_ratio = (
                        min(10.0, execution.active_seconds / execution.planned_seconds)
                        if execution.planned_seconds
                        and execution.planned_seconds > 0
                        and execution.evidence_status != "no_execution_evidence"
                        else None
                    )
                    InteractionTelemetryService.record(
                        event_data={
                            "event_type": InteractionTelemetryEventType.COMPLETION_FEEDBACK_RATE,
                            "interaction_type": artifact.type,
                            "actual_vs_planned_ratio": actual_vs_planned_ratio,
                        }
                    )
                if artifact.type == InteractionType.MEMORY_SUGGESTION and action == "accept":
                    InteractionTelemetryService.record(
                        event_data={
                            "event_type": InteractionTelemetryEventType.MEMORY_ACCEPTED,
                            "interaction_type": artifact.type,
                        }
                    )
        return InteractionSubmitResult(
            interaction=artifact,
            accepted=bool(result["accepted"]),
            plan=plan,
            detail=result.get("detail"),
            reason_codes=reason_codes,
            conflicts=conflicts,
            candidate=candidate,
        )

    @staticmethod
    def _parse_plan_items(values: dict[str, Any]) -> list[dict[str, Any]]:
        raw_items = values.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("items must be a non-empty list")
        edits: list[dict[str, Any]] = []
        for raw in raw_items:
            if not isinstance(raw, dict) or set(raw) - {"task_id", "start_at", "end_at", "locked"}:
                raise ValueError("Plan edit contains unsupported fields")
            task_id = raw.get("task_id")
            if not isinstance(task_id, str):
                raise ValueError("Each plan edit requires a task_id")
            edit: dict[str, Any] = {"task_id": UUID(task_id)}
            for field in ("start_at", "end_at"):
                if field in raw:
                    value = raw[field]
                    if not isinstance(value, str):
                        raise ValueError(f"{field} must be an ISO datetime")
                    try:
                        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except ValueError as exc:
                        raise ValueError(f"{field} must be an ISO datetime") from exc
                    if parsed.tzinfo is None or parsed.utcoffset() is None:
                        raise ValueError(f"{field} must include an explicit timezone")
                    edit[field] = parsed
            if "locked" in raw:
                if not isinstance(raw["locked"], bool):
                    raise ValueError("locked must be a boolean")
                edit["locked"] = raw["locked"]
            edits.append(edit)
        return edits

    @staticmethod
    def _validate_completion_feedback(values: dict[str, Any]) -> None:
        if set(values) - {"rating", "reason"}:
            raise ValueError("Completion feedback contains unsupported fields")
        if values.get("rating") not in {"faster", "about_right", "longer"}:
            raise ValueError("rating must be faster, about_right, or longer")
        reason = values.get("reason")
        if reason is not None and reason not in {
            "interrupted",
            "more_complex",
            "low_energy",
            "waiting",
            "other",
        }:
            raise ValueError("Unsupported completion feedback reason")

    @staticmethod
    def _record_memory_suggestion(
        *, user: User, task: Task, values: dict[str, Any], idempotency_key: str
    ) -> None:
        if values:
            raise ValueError("Memory suggestion consent accepts no client-supplied values")
        from apps.agents.memory.store import open_postgres_store

        with open_postgres_store() as store:
            recommendation = DecisionProfileService.recommend_duration(
                user=user, store=store, task_id=task.pk
            )
        original = recommendation.original_estimate_minutes
        recommended = recommendation.recommended_minutes
        if original is None or recommendation.sample_count < 3 or recommendation.confidence < 0.65:
            raise InteractionConflictError(
                "There is not enough duration evidence for this suggestion"
            )
        if recommended >= original * 1.25:
            action = TimeDecisionFeedbackAction.TOO_SHORT
        elif recommended <= original * 0.75:
            action = TimeDecisionFeedbackAction.TOO_LONG
        else:
            raise InteractionConflictError(
                "There is no material duration preference change to confirm"
            )
        DecisionProfileService.record_feedback(
            RecordDecisionFeedbackCommand(
                user=user,
                category=DURATION_CATEGORY,
                action=action,
                value={"segment": recommendation.segment},
                idempotency_key=f"interaction-memory:{idempotency_key}",
                source="web",
            )
        )


class InteractionTelemetryService:
    @staticmethod
    def record(*, event_data: dict[str, Any]) -> InteractionTelemetryEvent:
        event = InteractionTelemetryEvent(**event_data)
        event.full_clean()
        event.save(force_insert=True)
        return event

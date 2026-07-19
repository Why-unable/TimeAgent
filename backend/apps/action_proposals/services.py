from __future__ import annotations

import builtins
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.utils import timezone
from pydantic import TypeAdapter, ValidationError

from apps.action_proposals.models import ActionProposal, ActionProposalStatus
from apps.action_proposals.risk_policy import policy_for_tool
from apps.conversations.models import AgentRun
from apps.events.services import EventService
from apps.reminders.services import ReminderService
from apps.tasks.services import TaskService

DATETIME_ADAPTER = TypeAdapter(datetime)


class ProposalConflictError(ValueError):
    pass


class ProposalExpiredError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProposalDecision:
    proposal: ActionProposal
    resume_ready: bool


class ActionProposalService:
    @staticmethod
    @transaction.atomic
    def create_from_interrupt(
        *,
        run: AgentRun,
        interrupt_value: Any,
        interrupt_id: str | None = None,
    ) -> list[ActionProposal]:
        if not isinstance(interrupt_value, dict):
            raise ValueError("HITL interrupt payload must be an object")
        actions = interrupt_value.get("action_requests")
        configs = interrupt_value.get("review_configs")
        if (
            not isinstance(actions, list)
            or not isinstance(configs, list)
            or len(actions) != len(configs)
        ):
            raise ValueError("HITL interrupt payload is malformed")

        expires_at = timezone.now() + timedelta(
            seconds=getattr(settings, "ACTION_PROPOSAL_TTL_SECONDS", 86400)
        )
        proposals: list[ActionProposal] = []
        for index, (action, config) in enumerate(zip(actions, configs, strict=True)):
            if not isinstance(action, dict) or not isinstance(config, dict):
                raise ValueError("HITL action and review config must be objects")
            tool_name = str(action.get("name", ""))
            args = action.get("args")
            policy = policy_for_tool(tool_name)
            if policy is None or not isinstance(args, dict):
                raise ValueError("HITL action is not an approved high-risk tool")
            if config.get("action_name", tool_name) != tool_name:
                raise ValueError("HITL review config does not match its action")
            allowed_decisions = config.get("allowed_decisions")
            if allowed_decisions != list(policy.allowed_decisions):
                raise ValueError("HITL review decisions do not match the server risk policy")
            tool_call_id = f"pending:{interrupt_id or run.pk}:{index}"
            proposal, _ = ActionProposal.objects.get_or_create(
                agent_run=run,
                tool_call_id=tool_call_id,
                defaults={
                    "user": run.conversation.user,
                    "conversation": run.conversation,
                    "original_request": run.input_message,
                    "explanation": str(action.get("description", policy.description)),
                    "action_type": tool_name,
                    "action_payload": args,
                    "original_payload": args,
                    "display_context": ActionProposalService._display_context(
                        run=run,
                        tool_name=tool_name,
                        args=args,
                        allowed_decisions=allowed_decisions,
                        position=index,
                    ),
                    "risk_level": policy.risk_level,
                    "expires_at": expires_at,
                    "idempotency_key": f"{run.pk}:{tool_call_id}",
                },
            )
            proposals.append(proposal)
        return proposals

    @staticmethod
    @transaction.atomic
    def bind_tool_call(
        *,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ActionProposal | None:
        resolved_run_id = UUID(run_id)
        existing = ActionProposal.objects.filter(
            agent_run_id=resolved_run_id,
            tool_call_id=tool_call_id,
        ).first()
        if existing is not None:
            return existing
        proposal = (
            ActionProposal.objects.select_for_update()
            .filter(
                agent_run_id=resolved_run_id,
                action_type=tool_name,
                action_payload=arguments,
                status=ActionProposalStatus.APPROVED,
                resumed_at__isnull=False,
                tool_call_id__startswith="pending:",
            )
            .order_by("created_at", "id")
            .first()
        )
        if proposal is None:
            return None
        proposal.tool_call_id = tool_call_id
        proposal.save(update_fields=["tool_call_id", "updated_at"])
        return proposal

    @staticmethod
    def _display_context(
        *,
        run: AgentRun,
        tool_name: str,
        args: dict[str, Any],
        allowed_decisions: Any,
        position: int,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "allowed_decisions": allowed_decisions,
            "position": position,
            "object_name": str(args.get("title", "")),
            "impact_scope": "One high-risk operation",
            "proposed_start_at": args.get("start_at"),
            "proposed_end_at": args.get("end_at"),
            "is_recurring": bool(args.get("recurrence_rule")),
            "participants": args.get("participants", []),
            "reminder_settings": args.get("reminders", []),
            "conflicts": [],
        }
        if tool_name == "cancel_event":
            try:
                event = EventService.get_event(
                    user=run.conversation.user,
                    event_id=UUID(str(args.get("event_id", ""))),
                )
            except (ObjectDoesNotExist, TypeError, ValueError):
                context["target_lookup"] = "unavailable"
                return context
            context.update(
                {
                    "target_lookup": "completed",
                    "object_name": event.title,
                    "impact_scope": "Cancels one existing calendar event",
                    "proposed_start_at": event.start_at.isoformat(),
                    "proposed_end_at": event.end_at.isoformat(),
                    "current_status": event.status,
                    "current_version": event.version,
                    "is_recurring": bool(event.recurrence_rule),
                }
            )
            return context
        if tool_name == "cancel_reminder":
            try:
                reminder = ReminderService.get_reminder(
                    user=run.conversation.user,
                    reminder_id=UUID(str(args.get("reminder_id", ""))),
                )
            except (ObjectDoesNotExist, TypeError, ValueError):
                context["target_lookup"] = "unavailable"
                return context
            context.update(
                {
                    "target_lookup": "completed",
                    "object_name": reminder.title,
                    "impact_scope": "Cancels one pending reminder",
                    "proposed_start_at": reminder.trigger_at.isoformat(),
                    "current_status": reminder.status,
                }
            )
            return context
        if tool_name == "cancel_task":
            try:
                task = TaskService.get_task(
                    user=run.conversation.user,
                    task_id=UUID(str(args.get("task_id", ""))),
                )
            except (ObjectDoesNotExist, TypeError, ValueError):
                context["target_lookup"] = "unavailable"
                return context
            context.update(
                {
                    "target_lookup": "completed",
                    "object_name": task.title,
                    "impact_scope": "Cancels one active task without deleting it",
                    "proposed_start_at": (
                        task.planned_start_at.isoformat() if task.planned_start_at else None
                    ),
                    "proposed_end_at": (
                        task.planned_end_at.isoformat() if task.planned_end_at else None
                    ),
                    "due_at": task.due_at.isoformat() if task.due_at else None,
                    "current_status": task.status,
                }
            )
            return context
        if tool_name != "create_event":
            return context
        context["impact_scope"] = "Creates one confirmed event on the user's local calendar"
        try:
            start_at = DATETIME_ADAPTER.validate_python(args.get("start_at"))
            end_at = DATETIME_ADAPTER.validate_python(args.get("end_at"))
            conflicts = EventService.detect_conflicts(
                user=run.conversation.user,
                start_at=start_at,
                end_at=end_at,
            )
        except (ValidationError, ValueError, TypeError):
            context["conflict_check"] = "unavailable_until_arguments_are_valid"
            return context
        context["conflict_check"] = "completed"
        context["conflicts"] = [
            {
                "id": str(event.pk),
                "title": event.title,
                "start_at": event.start_at.isoformat(),
                "end_at": event.end_at.isoformat(),
            }
            for event in conflicts
        ]
        return context

    @staticmethod
    def list(*, user: User, status: str | None = None) -> list[ActionProposal]:
        ActionProposalService.expire_due(user=user)
        queryset = ActionProposal.objects.filter(user=user).select_related(
            "conversation", "agent_run"
        )
        if status:
            queryset = queryset.filter(status=status)
        return list(queryset)

    @staticmethod
    def get(*, user: User, proposal_id: UUID) -> ActionProposal:
        ActionProposalService.expire_due(user=user, proposal_id=proposal_id)
        return ActionProposal.objects.select_related("conversation", "agent_run").get(
            pk=proposal_id,
            user=user,
        )

    @staticmethod
    @transaction.atomic
    def decide(
        *,
        user: User,
        proposal_id: UUID,
        expected_version: int,
        decision: Literal["approve", "edit", "reject"],
        decision_idempotency_key: UUID,
        edited_payload: dict[str, Any] | None = None,
        reason: str = "",
    ) -> ProposalDecision:
        replay = ActionProposal.objects.filter(
            decision_idempotency_key=decision_idempotency_key,
            user=user,
        ).first()
        if replay is not None:
            if replay.pk != proposal_id or replay.decision_type != decision:
                raise ProposalConflictError("Decision idempotency key is already in use")
            return ProposalDecision(replay, ActionProposalService.resume_ready(replay.agent_run_id))

        proposal = ActionProposal.objects.select_for_update().get(pk=proposal_id, user=user)
        now = timezone.now()
        if proposal.status == ActionProposalStatus.AWAITING_APPROVAL and proposal.expires_at <= now:
            proposal.status = ActionProposalStatus.EXPIRED
            proposal.version += 1
            proposal.save(update_fields=["status", "version", "updated_at"])
            return ProposalDecision(proposal, False)
        if proposal.status != ActionProposalStatus.AWAITING_APPROVAL:
            raise ProposalConflictError("Action proposal is no longer awaiting approval")
        if proposal.version != expected_version:
            raise ProposalConflictError(
                "Action proposal version conflict: "
                f"expected {expected_version}, current {proposal.version}"
            )

        allowed = proposal.display_context.get("allowed_decisions", [])
        if decision not in allowed:
            raise ProposalConflictError(f"Decision {decision} is not allowed")
        if decision == "edit":
            if not isinstance(edited_payload, dict) or not edited_payload:
                raise ValueError("edited_payload is required for edit decisions")
            proposal.action_payload = edited_payload
        proposal.status = (
            ActionProposalStatus.REJECTED if decision == "reject" else ActionProposalStatus.APPROVED
        )
        proposal.decision_type = decision
        proposal.decision_reason = reason.strip()
        proposal.decision_idempotency_key = decision_idempotency_key
        proposal.decided_at = now
        proposal.approved_at = now if decision != "reject" else None
        proposal.version += 1
        proposal.save()
        return ProposalDecision(proposal, ActionProposalService.resume_ready(proposal.agent_run_id))

    @staticmethod
    def resume_ready(run_id: UUID) -> bool:
        statuses = set(
            ActionProposal.objects.filter(agent_run_id=run_id, resumed_at__isnull=True).values_list(
                "status", flat=True
            )
        )
        return bool(statuses) and ActionProposalStatus.AWAITING_APPROVAL not in statuses

    @staticmethod
    def resume_payload(run_id: UUID) -> dict[str, builtins.list[dict[str, Any]]]:
        proposals = builtins.list(
            ActionProposal.objects.filter(agent_run_id=run_id, resumed_at__isnull=True).order_by(
                "created_at", "id"
            )
        )
        if not proposals or any(
            proposal.status == ActionProposalStatus.AWAITING_APPROVAL for proposal in proposals
        ):
            raise ProposalConflictError("Not all pending actions have decisions")
        decisions: builtins.list[dict[str, Any]] = []
        for proposal in proposals:
            if proposal.status == ActionProposalStatus.EXPIRED:
                decisions.append({"type": "reject", "message": "Approval expired before execution"})
            elif proposal.decision_type == "edit":
                decisions.append(
                    {
                        "type": "edit",
                        "edited_action": {
                            "name": proposal.action_type,
                            "args": proposal.action_payload,
                        },
                    }
                )
            elif proposal.decision_type == "reject":
                decisions.append(
                    {
                        "type": "reject",
                        "message": proposal.decision_reason or "User rejected this action",
                    }
                )
            else:
                decisions.append({"type": "approve"})
        return {"decisions": decisions}

    @staticmethod
    def mark_resumed(run_id: UUID) -> None:
        ActionProposal.objects.filter(
            agent_run_id=run_id,
            resumed_at__isnull=True,
        ).exclude(status=ActionProposalStatus.AWAITING_APPROVAL).update(
            resumed_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def mark_executing(*, run_id: str, tool_call_id: str) -> None:
        resolved_run_id = UUID(run_id)
        ActionProposal.objects.filter(
            agent_run_id=resolved_run_id,
            tool_call_id=tool_call_id,
            status=ActionProposalStatus.APPROVED,
        ).update(status=ActionProposalStatus.EXECUTING, updated_at=timezone.now())

    @staticmethod
    @transaction.atomic
    def mark_executed(*, run_id: str, tool_call_id: str, result: Any) -> None:
        resolved_run_id = UUID(run_id)
        ActionProposal.objects.filter(
            agent_run_id=resolved_run_id,
            tool_call_id=tool_call_id,
            status__in=[ActionProposalStatus.APPROVED, ActionProposalStatus.EXECUTING],
        ).update(
            status=ActionProposalStatus.EXECUTED,
            execution_result=result,
            executed_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def mark_failed(*, run_id: str, tool_call_id: str, error: Exception) -> None:
        resolved_run_id = UUID(run_id)
        ActionProposal.objects.filter(
            agent_run_id=resolved_run_id,
            tool_call_id=tool_call_id,
            status__in=[ActionProposalStatus.APPROVED, ActionProposalStatus.EXECUTING],
        ).update(
            status=ActionProposalStatus.FAILED,
            error=f"{type(error).__name__}: {error}"[:4000],
            updated_at=timezone.now(),
        )

    @staticmethod
    def expire_due(*, user: User, proposal_id: UUID | None = None) -> int:
        queryset = ActionProposal.objects.filter(
            user=user,
            status=ActionProposalStatus.AWAITING_APPROVAL,
            expires_at__lte=timezone.now(),
        )
        if proposal_id is not None:
            queryset = queryset.filter(pk=proposal_id)
        return queryset.update(
            status=ActionProposalStatus.EXPIRED,
            version=models.F("version") + 1,
            updated_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def expire_due_runs(*, now: datetime | None = None) -> set[UUID]:
        current_time = now or timezone.now()
        due = list(
            ActionProposal.objects.select_for_update()
            .filter(
                status=ActionProposalStatus.AWAITING_APPROVAL,
                expires_at__lte=current_time,
            )
            .values_list("pk", "agent_run_id")
        )
        if not due:
            return set()
        ActionProposal.objects.filter(pk__in=[proposal_id for proposal_id, _ in due]).update(
            status=ActionProposalStatus.EXPIRED,
            version=models.F("version") + 1,
            updated_at=current_time,
        )
        return {run_id for _, run_id in due}

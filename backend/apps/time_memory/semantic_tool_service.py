from typing import cast
from uuid import UUID

from django.contrib.auth.models import User

from apps.action_proposals.models import ActionProposal
from apps.action_proposals.services import ActionProposalService
from apps.conversations.models import AgentRun
from apps.preferences.services import UserPreferenceService
from apps.time_memory.explicit_intent import ExplicitMemoryIntent
from apps.time_memory.models import MemoryProposalSource, SemanticMemory, SemanticMemoryStatus
from apps.time_memory.semantic_schemas import MemoryProposalPayload, SemanticMemoryCategory
from apps.time_memory.semantic_services import ProposalResult, SemanticMemoryService
from apps.time_memory.settings import get_time_memory_settings


class SemanticMemoryToolService:
    """Application boundary for model-invoked semantic-memory tools."""

    @staticmethod
    def search(
        *,
        user: User,
        query: str = "",
        category: str | None = None,
        limit: int = 10,
    ) -> list[SemanticMemory]:
        SemanticMemoryToolService._require_enabled(user=user, write=False)
        return SemanticMemoryService.search(
            user=user,
            query=query,
            category=category,
            limit=limit,
        )

    @staticmethod
    def remember(
        *,
        user: User,
        run_id: str,
        category: SemanticMemoryCategory,
        key: str,
        value: dict[str, object],
        idempotency_key: str,
        tool_call_id: str = "",
    ) -> ProposalResult:
        SemanticMemoryToolService._require_enabled(user=user, write=True)
        run = SemanticMemoryToolService._source_run(user=user, run_id=run_id)
        approval = SemanticMemoryToolService._approved_action(
            user=user,
            run=run,
            tool_call_id=tool_call_id,
            tool_name="remember_time_preference",
            arguments={"category": category, "key": key, "value": value},
        )
        SemanticMemoryToolService._validate_snapshot(
            user=user,
            approval=approval,
            category=category,
            key="_".join(key.strip().casefold().split()),
        )
        result = SemanticMemoryService.create_proposal(
            user=user,
            source_run=run,
            source_type=MemoryProposalSource.AGENT_TOOL,
            idempotency_key=idempotency_key,
            explicit_user_authorized=ExplicitMemoryIntent.authorizes(
                operation="create",
                user_message=run.input_message,
            ),
            direct_apply_mode=SemanticMemoryToolService._direct_apply_mode(approval),
            payload=MemoryProposalPayload(
                operation="create",
                category=category,
                key=key,
                value=value,
                confidence=1.0,
                evidence_excerpt=run.input_message[:1000],
                reason_code="explicit_agent_tool_intent",
            ),
        )
        return SemanticMemoryToolService._finalize(user=user, result=result, approval=approval)

    @staticmethod
    def update(
        *,
        user: User,
        run_id: str,
        memory_id: UUID,
        value: dict[str, object],
        idempotency_key: str,
        tool_call_id: str = "",
    ) -> ProposalResult:
        SemanticMemoryToolService._require_enabled(user=user, write=True)
        run = SemanticMemoryToolService._source_run(user=user, run_id=run_id)
        target = SemanticMemoryToolService._target(user=user, memory_id=memory_id)
        approval = SemanticMemoryToolService._approved_action(
            user=user,
            run=run,
            tool_call_id=tool_call_id,
            tool_name="update_time_preference",
            arguments={"memory_id": str(memory_id), "value": value},
        )
        SemanticMemoryToolService._validate_snapshot(
            user=user,
            approval=approval,
            memory_id=memory_id,
        )
        result = SemanticMemoryService.create_proposal(
            user=user,
            source_run=run,
            source_type=MemoryProposalSource.AGENT_TOOL,
            target_memory=target,
            idempotency_key=idempotency_key,
            explicit_user_authorized=ExplicitMemoryIntent.authorizes(
                operation="update",
                user_message=run.input_message,
            ),
            direct_apply_mode=SemanticMemoryToolService._direct_apply_mode(approval),
            payload=MemoryProposalPayload(
                operation="update",
                category=cast(SemanticMemoryCategory, target.category),
                key=target.key,
                value=value,
                confidence=1.0,
                evidence_excerpt=run.input_message[:1000],
                reason_code="explicit_agent_tool_intent",
            ),
        )
        return SemanticMemoryToolService._finalize(user=user, result=result, approval=approval)

    @staticmethod
    def forget(
        *,
        user: User,
        run_id: str,
        memory_id: UUID,
        idempotency_key: str,
        tool_call_id: str = "",
    ) -> ProposalResult:
        SemanticMemoryToolService._require_enabled(user=user, write=True)
        run = SemanticMemoryToolService._source_run(user=user, run_id=run_id)
        target = SemanticMemoryToolService._target(user=user, memory_id=memory_id)
        approval = SemanticMemoryToolService._approved_action(
            user=user,
            run=run,
            tool_call_id=tool_call_id,
            tool_name="forget_time_preference",
            arguments={"memory_id": str(memory_id)},
        )
        SemanticMemoryToolService._validate_snapshot(
            user=user,
            approval=approval,
            memory_id=memory_id,
        )
        result = SemanticMemoryService.create_proposal(
            user=user,
            source_run=run,
            source_type=MemoryProposalSource.AGENT_TOOL,
            target_memory=target,
            idempotency_key=idempotency_key,
            explicit_user_authorized=ExplicitMemoryIntent.authorizes(
                operation="delete",
                user_message=run.input_message,
            ),
            direct_apply_mode=SemanticMemoryToolService._direct_apply_mode(approval),
            payload=MemoryProposalPayload(
                operation="delete",
                category=cast(SemanticMemoryCategory, target.category),
                key=target.key,
                value={},
                confidence=1.0,
                evidence_excerpt=run.input_message[:1000],
                reason_code="explicit_agent_tool_intent",
            ),
        )
        return SemanticMemoryToolService._finalize(user=user, result=result, approval=approval)

    @staticmethod
    def _approved_action(
        *,
        user: User,
        run: AgentRun,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> ActionProposal | None:
        if not get_time_memory_settings().agent_inline_approval_enabled:
            return None
        if not tool_call_id.strip():
            raise PermissionError("Inline memory approval requires a trusted tool call ID")
        try:
            return ActionProposalService.get_approved_tool_execution(
                user=user,
                run_id=str(run.pk),
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=arguments,
            )
        except ActionProposal.DoesNotExist as exc:
            raise PermissionError("Memory tool execution has not been approved") from exc

    @staticmethod
    def _validate_snapshot(
        *,
        user: User,
        approval: ActionProposal | None,
        category: str | None = None,
        key: str | None = None,
        memory_id: UUID | None = None,
    ) -> None:
        if approval is None:
            return
        if memory_id is not None:
            current = SemanticMemory.objects.filter(
                pk=memory_id,
                user=user,
                status=SemanticMemoryStatus.ACTIVE,
            ).first()
        else:
            current = SemanticMemory.objects.filter(
                user=user,
                category=category,
                key=key,
                status=SemanticMemoryStatus.ACTIVE,
            ).first()
        expected_id = approval.display_context.get("memory_target_id")
        expected_version = approval.display_context.get("memory_target_version")
        if expected_id is None:
            matches = current is None
        else:
            matches = (
                current is not None
                and str(current.pk) == str(expected_id)
                and current.version == expected_version
            )
        if not matches:
            error = ValueError("Memory changed after approval was requested; review it again")
            ActionProposalService.mark_failed(
                run_id=str(approval.agent_run_id),
                tool_call_id=approval.tool_call_id,
                error=error,
            )
            raise error

    @staticmethod
    def _finalize(
        *,
        user: User,
        result: ProposalResult,
        approval: ActionProposal | None,
    ) -> ProposalResult:
        if approval is None or result.proposal.status != "pending":
            return result
        proposal = SemanticMemoryService.decide_proposal(
            user=user,
            proposal_id=result.proposal.pk,
            approve=True,
        )
        return ProposalResult(proposal=proposal, action="applied")

    @staticmethod
    def _direct_apply_mode(approval: ActionProposal | None) -> str:
        if approval is not None:
            return "confirm"
        return get_time_memory_settings().agent_direct_apply_mode

    @staticmethod
    def _require_enabled(*, user: User, write: bool) -> None:
        preference = UserPreferenceService.get_for_user(user)
        if preference is None or not preference.time_memory_enabled:
            raise PermissionError("Time memory is disabled for this user")
        if write and not preference.time_memory_allow_generation:
            raise PermissionError("Time memory generation is disabled for this user")

    @staticmethod
    def _source_run(*, user: User, run_id: str) -> AgentRun:
        if not run_id.strip():
            raise ValueError("Memory write tools require an AgentRun")
        run = AgentRun.objects.filter(pk=run_id, conversation__user=user).first()
        if run is None:
            raise AgentRun.DoesNotExist
        if not run.input_message.strip():
            raise ValueError("Memory write tools require a user message")
        return run

    @staticmethod
    def _target(*, user: User, memory_id: UUID) -> SemanticMemory:
        return SemanticMemory.objects.get(
            pk=memory_id,
            user=user,
            status=SemanticMemoryStatus.ACTIVE,
        )

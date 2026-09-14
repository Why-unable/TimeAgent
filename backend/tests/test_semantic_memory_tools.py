from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from langchain.tools import ToolRuntime
from langchain_core.tools import StructuredTool

from apps.agents.context import RuntimeContext
from apps.agents.tools.memory_tools import (
    forget_time_preference,
    remember_time_preference,
    search_time_memories,
    update_time_preference,
)
from apps.conversations.models import AgentRun, AgentRunStatus, Conversation
from apps.preferences.services import UserPreferenceService
from apps.time_memory.models import (
    MemoryProposal,
    MemoryProposalSource,
    MemoryProposalStatus,
    SemanticMemory,
    SemanticMemorySource,
    SemanticMemoryStatus,
)
from apps.time_memory.semantic_services import SemanticMemoryService

pytestmark = pytest.mark.django_db


def _runtime(*, user: Any, run: AgentRun, tool_call_id: str) -> ToolRuntime[RuntimeContext, Any]:
    context = RuntimeContext(
        user_id=str(user.pk),
        request_id=str(uuid4()),
        timezone="Asia/Shanghai",
        locale="zh-CN",
        current_datetime=datetime(2026, 8, 31, tzinfo=UTC),
        trigger_type="user_message",
        conversation_id=str(run.conversation_id),
        agent_run_id=str(run.pk),
        input_message=run.input_message,
        actor=user,
    )
    return ToolRuntime[RuntimeContext, Any](
        state={"messages": []},
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id=tool_call_id,
        store=None,
        tools=[],
    )


def _run(*, user: Any, message: str) -> AgentRun:
    preference = UserPreferenceService.get_or_create_for_user(user)
    preference.time_memory_enabled = True
    preference.time_memory_allow_generation = True
    preference.save(update_fields=["time_memory_enabled", "time_memory_allow_generation"])
    conversation = Conversation.objects.create(user=user, title="memory tools")
    return AgentRun.objects.create(
        conversation=conversation,
        operation_id=uuid4(),
        request_id=str(uuid4()),
        status=AgentRunStatus.RUNNING,
        input_message=message,
        anchor_at=datetime(2026, 8, 31, tzinfo=UTC),
        anchor_timezone="Asia/Shanghai",
    )


def _function(tool: object) -> Any:
    function = cast(StructuredTool, tool).func
    assert function is not None
    return function


@override_settings(TIME_MEMORY_AGENT_SEARCH_TOOL_ENABLED=True)
def test_search_tool_is_user_scoped_and_bounded() -> None:
    user = get_user_model().objects.create_user(username=f"memory-tool-{uuid4()}")
    other = get_user_model().objects.create_user(username=f"memory-tool-{uuid4()}")
    run = _run(user=user, message="我之前关于周五会议的偏好是什么？")
    own = SemanticMemory.objects.create(
        user=user,
        category="scheduling_preference",
        key="friday_meetings",
        value={"avoid": True},
        source_type=SemanticMemorySource.EXPLICIT_USER,
        confidence=1,
    )
    SemanticMemory.objects.create(
        user=other,
        category="scheduling_preference",
        key="friday_meetings",
        value={"avoid": False},
        source_type=SemanticMemorySource.EXPLICIT_USER,
        confidence=1,
    )

    result = _function(search_time_memories)(
        runtime=_runtime(user=user, run=run, tool_call_id="search-1"),
        query="friday",
        limit=50,
    )

    assert result == {
        "results": [
            {
                "id": str(own.pk),
                "category": "scheduling_preference",
                "key": "friday_meetings",
                "value": {"avoid": True},
                "version": 1,
            }
        ],
        "count": 1,
    }


@override_settings(TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=True)
def test_remember_tool_creates_one_pending_proposal_without_applying_memory() -> None:
    user = get_user_model().objects.create_user(username=f"memory-tool-{uuid4()}")
    run = _run(user=user, message="请记住以后周五下午不要安排会议")
    runtime = _runtime(user=user, run=run, tool_call_id="remember-1")
    function = _function(remember_time_preference)

    first = function(
        category="scheduling_preference",
        key="friday afternoon meetings",
        value={"avoid": True},
        runtime=runtime,
    )
    second = function(
        category="scheduling_preference",
        key="friday afternoon meetings",
        value={"avoid": True},
        runtime=runtime,
    )

    proposal = MemoryProposal.objects.get()
    assert first == second
    assert first["status"] == MemoryProposalStatus.PENDING
    assert first["requires_confirmation"] is True
    assert proposal.source_type == MemoryProposalSource.AGENT_TOOL
    assert proposal.source_run_id == run.pk
    assert SemanticMemory.objects.count() == 0


@override_settings(
    TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=True,
    TIME_MEMORY_AGENT_DIRECT_APPLY_MODE="enabled",
)
def test_explicit_low_risk_remember_tool_applies_without_second_confirmation() -> None:
    user = get_user_model().objects.create_user(username=f"memory-tool-{uuid4()}")
    run = _run(user=user, message="请记住以后周五下午不要安排会议")

    result = _function(remember_time_preference)(
        category="scheduling_preference",
        key="friday afternoon meetings",
        value={"avoid": True},
        runtime=_runtime(user=user, run=run, tool_call_id="remember-direct-1"),
    )

    assert result["status"] == MemoryProposalStatus.APPLIED
    assert result["requires_confirmation"] is False
    assert result["can_undo"] is True
    assert SemanticMemory.objects.get(user=user).value == {"avoid": True}


@override_settings(
    TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=True,
    TIME_MEMORY_AGENT_DIRECT_APPLY_MODE="enabled",
)
def test_non_explicit_or_high_impact_memory_still_requires_confirmation() -> None:
    user = get_user_model().objects.create_user(username=f"memory-tool-{uuid4()}")
    implicit_run = _run(user=user, message="我一般喜欢上午做专注工作")
    implicit = _function(remember_time_preference)(
        category="scheduling_preference",
        key="focus period",
        value={"period": "morning"},
        runtime=_runtime(user=user, run=implicit_run, tool_call_id="remember-implicit-1"),
    )
    high_impact_run = _run(user=user, message="请记住周五下午绝对不能安排任何事情")
    high_impact = _function(remember_time_preference)(
        category="availability_constraint",
        key="friday afternoon unavailable",
        value={"unavailable": True},
        runtime=_runtime(user=user, run=high_impact_run, tool_call_id="remember-hard-1"),
    )

    assert implicit["status"] == MemoryProposalStatus.PENDING
    assert high_impact["status"] == MemoryProposalStatus.PENDING
    assert SemanticMemory.objects.count() == 0


@override_settings(
    TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=True,
    TIME_MEMORY_AGENT_INLINE_APPROVAL_ENABLED=True,
)
def test_inline_memory_tool_rejects_execution_without_resumed_action_approval() -> None:
    user = get_user_model().objects.create_user(username=f"memory-tool-{uuid4()}")
    run = _run(user=user, message="请记住以后周五下午不要安排会议")

    with pytest.raises(PermissionError, match="has not been approved"):
        _function(remember_time_preference)(
            category="scheduling_preference",
            key="friday afternoon meetings",
            value={"avoid": True},
            runtime=_runtime(user=user, run=run, tool_call_id="unapproved-memory-write"),
        )

    assert MemoryProposal.objects.count() == 0
    assert SemanticMemory.objects.count() == 0


@override_settings(TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=True)
def test_approved_remember_tool_proposal_becomes_explicit_memory() -> None:
    user = get_user_model().objects.create_user(username=f"memory-tool-{uuid4()}")
    run = _run(user=user, message="请记住我更喜欢上午处理专注任务")
    result = _function(remember_time_preference)(
        category="scheduling_preference",
        key="focus period",
        value={"period": "morning"},
        runtime=_runtime(user=user, run=run, tool_call_id="remember-2"),
    )

    SemanticMemoryService.decide_proposal(
        user=user,
        proposal_id=result["proposal_id"],
        approve=True,
    )

    memory = SemanticMemory.objects.get(user=user)
    assert memory.source_type == SemanticMemorySource.EXPLICIT_USER
    assert memory.value == {"period": "morning"}


@override_settings(TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=True)
def test_update_proposal_conflicts_when_target_version_changes_before_approval() -> None:
    user = get_user_model().objects.create_user(username=f"memory-tool-{uuid4()}")
    run = _run(user=user, message="把我的专注时间改成下午")
    memory = SemanticMemory.objects.create(
        user=user,
        category="scheduling_preference",
        key="focus_period",
        value={"period": "morning"},
        source_type=SemanticMemorySource.EXPLICIT_USER,
        confidence=1,
    )
    result = _function(update_time_preference)(
        memory_id=memory.pk,
        value={"period": "afternoon"},
        runtime=_runtime(user=user, run=run, tool_call_id="update-1"),
    )
    memory.version = 2
    memory.value = {"period": "evening"}
    memory.save(update_fields=["version", "value", "updated_at"])

    proposal = SemanticMemoryService.decide_proposal(
        user=user,
        proposal_id=result["proposal_id"],
        approve=True,
    )

    memory.refresh_from_db()
    assert proposal.status == MemoryProposalStatus.CONFLICTED
    assert proposal.policy_reason == "target_version_conflict"
    assert memory.status == SemanticMemoryStatus.ACTIVE
    assert memory.value == {"period": "evening"}


@override_settings(TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=True)
def test_forget_tool_cannot_target_another_users_memory() -> None:
    user = get_user_model().objects.create_user(username=f"memory-tool-{uuid4()}")
    other = get_user_model().objects.create_user(username=f"memory-tool-{uuid4()}")
    run = _run(user=user, message="忘记那条偏好")
    foreign = SemanticMemory.objects.create(
        user=other,
        category="scheduling_preference",
        key="focus_period",
        value={"period": "morning"},
        source_type=SemanticMemorySource.EXPLICIT_USER,
        confidence=1,
    )

    with pytest.raises(SemanticMemory.DoesNotExist):
        _function(forget_time_preference)(
            memory_id=foreign.pk,
            runtime=_runtime(user=user, run=run, tool_call_id="forget-1"),
        )

    assert MemoryProposal.objects.count() == 0

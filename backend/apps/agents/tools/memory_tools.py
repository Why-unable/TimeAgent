from typing import Any
from uuid import UUID

from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import require_actor, require_writable, tool_idempotency_key
from apps.time_memory.semantic_schemas import SemanticMemoryCategory
from apps.time_memory.semantic_tool_service import SemanticMemoryToolService
from apps.time_memory.settings import get_time_memory_settings


def _require_search_enabled() -> None:
    if not get_time_memory_settings().agent_search_tool_enabled:
        raise PermissionError("Semantic memory search tool is disabled")


def _require_write_enabled() -> None:
    if not get_time_memory_settings().agent_write_tools_enabled:
        raise PermissionError("Semantic memory write tools are disabled")


def _proposal_result(result: Any) -> dict[str, object]:
    proposal = result.proposal
    return {
        "proposal_id": str(proposal.pk),
        "status": proposal.status,
        "requires_confirmation": proposal.status == "pending",
        "can_undo": proposal.can_undo,
    }


@tool
def search_time_memories(
    runtime: ToolRuntime[RuntimeContext, Any],
    query: str = "",
    category: SemanticMemoryCategory | None = None,
    limit: int = 10,
) -> dict[str, object]:
    """Search the authenticated user's confirmed long-term time preferences.

    Use this before relying on an older preference or before proposing an update or deletion.
    Results contain only active, unexpired memories owned by the current user.
    """

    _require_search_enabled()
    memories = SemanticMemoryToolService.search(
        user=require_actor(runtime),
        query=query,
        category=category,
        limit=limit,
    )
    results = [
        {
            "id": str(memory.pk),
            "category": memory.category,
            "key": memory.key,
            "value": memory.value,
            "version": memory.version,
        }
        for memory in memories
    ]
    return {"results": results, "count": len(results)}


@tool
def remember_time_preference(
    category: SemanticMemoryCategory,
    key: str,
    value: dict[str, object],
    runtime: ToolRuntime[RuntimeContext, Any],
) -> dict[str, object]:
    """Remember a durable time-management preference through the memory policy.

    Use only when the current user explicitly asks to remember the preference. The policy
    may apply a low-risk command when direct apply is enabled; otherwise it returns a
    proposal for inline review or the memory management page.
    """

    _require_write_enabled()
    actor = require_writable(runtime)
    return _proposal_result(
        SemanticMemoryToolService.remember(
            user=actor,
            run_id=runtime.context.agent_run_id or "",
            category=category,
            key=key,
            value=value,
            idempotency_key=tool_idempotency_key(runtime, purpose="remember-time-preference"),
            tool_call_id=str(runtime.tool_call_id or ""),
        )
    )


@tool
def update_time_preference(
    memory_id: UUID,
    value: dict[str, object],
    runtime: ToolRuntime[RuntimeContext, Any],
) -> dict[str, object]:
    """Update one confirmed time preference through the memory policy.

    Call search_time_memories first to obtain the current memory ID. The existing memory
    remains active until approval succeeds.
    """

    _require_write_enabled()
    actor = require_writable(runtime)
    return _proposal_result(
        SemanticMemoryToolService.update(
            user=actor,
            run_id=runtime.context.agent_run_id or "",
            memory_id=memory_id,
            value=value,
            idempotency_key=tool_idempotency_key(runtime, purpose="update-time-preference"),
            tool_call_id=str(runtime.tool_call_id or ""),
        )
    )


@tool
def forget_time_preference(
    memory_id: UUID,
    runtime: ToolRuntime[RuntimeContext, Any],
) -> dict[str, object]:
    """Forget one confirmed time preference through the memory policy.

    Call search_time_memories first to obtain the current memory ID. The memory remains
    active until approval succeeds.
    """

    _require_write_enabled()
    actor = require_writable(runtime)
    return _proposal_result(
        SemanticMemoryToolService.forget(
            user=actor,
            run_id=runtime.context.agent_run_id or "",
            memory_id=memory_id,
            idempotency_key=tool_idempotency_key(runtime, purpose="forget-time-preference"),
            tool_call_id=str(runtime.tool_call_id or ""),
        )
    )


MEMORY_READ_TOOLS = [search_time_memories]
MEMORY_WRITE_TOOLS = [
    remember_time_preference,
    update_time_preference,
    forget_time_preference,
]

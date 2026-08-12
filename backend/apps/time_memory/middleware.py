from collections.abc import Awaitable, Callable
from typing import Any

from asgiref.sync import sync_to_async
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command, Overwrite

from apps.agents.context import RuntimeContext
from apps.agents.state import TimeStewardState
from apps.preferences.services import UserPreferenceService
from apps.time_memory.prompt_renderer import render_memory_prompt
from apps.time_memory.ranking import classify_memory_intent
from apps.time_memory.repository import TimeMemoryRepository
from apps.time_memory.schemas import TimeMemoryProfile
from apps.time_memory.settings import get_time_memory_settings

WRITE_MEMORY_TOOLS = frozenset(
    {
        "create_event",
        "create_event_batch",
        "mutate_events",
        "create_recurring_event",
        "cancel_event",
        "create_task",
        "create_task_batch",
        "update_task",
        "change_task_state",
        "change_task_batch_state",
        "complete_task",
        "cancel_task",
        "reschedule_task",
        "apply_schedule_plan",
        "create_reminder",
        "update_reminder",
        "set_reminder_target",
        "cancel_reminder",
    }
)


class TimeMemoryMiddleware(AgentMiddleware[TimeStewardState, RuntimeContext, Any]):
    state_schema = TimeStewardState

    def before_agent(
        self,
        state: TimeStewardState,
        runtime: Runtime[RuntimeContext],
    ) -> dict[str, Any] | None:
        context = runtime.context
        if context.actor is None or runtime.store is None:
            return {"time_memory_profile": None, "schedule_changed": Overwrite(False)}
        preference = UserPreferenceService.get_for_user(context.actor)
        if (
            preference is None
            or not preference.time_memory_enabled
            or not preference.time_memory_allow_context_injection
        ):
            return {"time_memory_profile": None, "schedule_changed": Overwrite(False)}
        profile = TimeMemoryRepository.get(runtime.store, user_id=context.user_id)
        return {
            "time_memory_profile": (
                profile.model_dump(mode="json") if profile is not None else None
            ),
            "schedule_changed": Overwrite(False),
        }

    async def abefore_agent(
        self,
        state: TimeStewardState,
        runtime: Runtime[RuntimeContext],
    ) -> dict[str, Any] | None:
        context = runtime.context
        if context.actor is None or runtime.store is None:
            return {"time_memory_profile": None, "schedule_changed": Overwrite(False)}
        preference = await sync_to_async(UserPreferenceService.get_for_user)(context.actor)
        if (
            preference is None
            or not preference.time_memory_enabled
            or not preference.time_memory_allow_context_injection
        ):
            return {"time_memory_profile": None, "schedule_changed": Overwrite(False)}
        profile = await TimeMemoryRepository.aget(runtime.store, user_id=context.user_id)
        return {
            "time_memory_profile": (
                profile.model_dump(mode="json") if profile is not None else None
            ),
            "schedule_changed": Overwrite(False),
        }

    @staticmethod
    def _latest_user_text(request: ModelRequest[RuntimeContext]) -> str:
        for message in reversed(request.messages):
            if isinstance(message, HumanMessage):
                return message.text
        return ""

    def wrap_model_call(
        self,
        request: ModelRequest[RuntimeContext],
        handler: Callable[[ModelRequest[RuntimeContext]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(self._request(request))

    def _request(
        self,
        request: ModelRequest[RuntimeContext],
    ) -> ModelRequest[RuntimeContext]:
        raw_profile = request.state.get("time_memory_profile")
        if not isinstance(raw_profile, dict):
            return request
        profile = TimeMemoryProfile.model_validate(raw_profile)
        prompt = render_memory_prompt(
            profile,
            classify_memory_intent(self._latest_user_text(request)),
            token_budget=get_time_memory_settings().prompt_token_budget,
            token_counter=request.model.get_num_tokens,
            now=request.runtime.context.current_datetime,
        )
        if not prompt:
            return request
        system_message = request.system_message or SystemMessage(content="")
        content = system_message.content
        blocks = (
            [{"type": "text", "text": content}, {"type": "text", "text": prompt}]
            if isinstance(content, str)
            else [*content, {"type": "text", "text": prompt}]
        )
        return request.override(
            system_message=system_message.model_copy(update={"content": blocks})
        )

    async def awrap_model_call(
        self,
        request: ModelRequest[RuntimeContext],
        handler: Callable[
            [ModelRequest[RuntimeContext]],
            Awaitable[ModelResponse[Any]],
        ],
    ) -> ModelResponse[Any]:
        return await handler(self._request(request))

    @staticmethod
    def _mark_changed(result: ToolMessage | Command[Any]) -> Command[Any] | ToolMessage:
        if isinstance(result, ToolMessage):
            if result.status == "error":
                return result
            return Command(update={"messages": [result], "schedule_changed": True})
        if isinstance(result.update, dict):
            return Command(
                graph=result.graph,
                update={**result.update, "schedule_changed": True},
                resume=result.resume,
                goto=result.goto,
            )
        return result

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        result = handler(request)
        if request.tool_call.get("name") not in WRITE_MEMORY_TOOLS:
            return result
        return self._mark_changed(result)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        result = await handler(request)
        if request.tool_call.get("name") not in WRITE_MEMORY_TOOLS:
            return result
        return self._mark_changed(result)

    def after_agent(
        self,
        state: TimeStewardState,
        runtime: Runtime[RuntimeContext],
    ) -> dict[str, Any] | None:
        if not state.get("schedule_changed") or runtime.context.actor is None:
            return None
        from apps.time_memory.event_handler import mark_time_memory_dirty

        mark_time_memory_dirty(user=runtime.context.actor)
        return None

    async def aafter_agent(
        self,
        state: TimeStewardState,
        runtime: Runtime[RuntimeContext],
    ) -> dict[str, Any] | None:
        if not state.get("schedule_changed") or runtime.context.actor is None:
            return None
        from apps.time_memory.event_handler import mark_time_memory_dirty

        await sync_to_async(mark_time_memory_dirty)(user=runtime.context.actor)
        return None

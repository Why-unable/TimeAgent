from typing import Any

from langchain.agents import create_agent
from langchain_core.callbacks.base import Callbacks
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from apps.agents.context import RuntimeContext
from apps.agents.middleware import build_time_steward_middleware
from apps.agents.model import build_chat_model, build_fallback_chat_models
from apps.agents.state import TimeStewardState
from apps.agents.tool_discovery import (
    ToolDiscoverySettings,
    resolve_tool_discovery_settings,
)
from apps.agents.tools import TIME_STEWARD_TOOLS


def build_time_steward_agent(
    *,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
    temporal_context_enabled: bool = True,
    compact_planning_surface: bool = True,
    discovery_settings: ToolDiscoverySettings | None = None,
    selector_model: BaseChatModel | None = None,
    selector_callbacks: Callbacks | None = None,
    fallback_models: list[BaseChatModel] | None = None,
) -> Runnable[Any, Any]:
    resolved_model = model or build_chat_model()
    resolved_fallback_models = (
        fallback_models
        if fallback_models is not None
        else ([] if model is not None else build_fallback_chat_models())
    )
    settings = resolve_tool_discovery_settings(discovery_settings)
    resolved_selector_model = selector_model
    if resolved_selector_model is None and settings.selector_model_alias:
        resolved_selector_model = build_chat_model(
            settings.selector_model_alias,
            callbacks=selector_callbacks,
        )
    elif selector_callbacks is not None and resolved_selector_model is not None:
        raise ValueError("Pass selector_callbacks with a configured selector_model alias")
    return create_agent(
        model=resolved_model,
        tools=TIME_STEWARD_TOOLS,
        middleware=build_time_steward_middleware(
            resolved_model,
            fallback_models=resolved_fallback_models,
            temporal_context_enabled=temporal_context_enabled,
            compact_planning_surface=compact_planning_surface,
            discovery_settings=settings,
            selector_model=resolved_selector_model,
        ),
        state_schema=TimeStewardState,
        context_schema=RuntimeContext,
        checkpointer=checkpointer,
        store=store,
        name="time_steward",
    )

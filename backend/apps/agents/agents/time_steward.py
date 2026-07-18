from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from apps.agents.context import RuntimeContext
from apps.agents.middleware import build_time_steward_middleware
from apps.agents.model import build_chat_model, build_fallback_chat_models
from apps.agents.state import TimeStewardState
from apps.agents.tools import TIME_STEWARD_TOOLS


def build_time_steward_agent(
    *,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
) -> Runnable[Any, Any]:
    resolved_model = model or build_chat_model()
    fallback_models = [] if model is not None else build_fallback_chat_models()
    return create_agent(
        model=resolved_model,
        tools=TIME_STEWARD_TOOLS,
        middleware=build_time_steward_middleware(
            resolved_model,
            fallback_models=fallback_models,
        ),
        state_schema=TimeStewardState,
        context_schema=RuntimeContext,
        checkpointer=checkpointer,
        store=store,
        name="time_steward",
    )

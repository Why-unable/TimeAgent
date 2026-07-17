from importlib.metadata import version
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    SummarizationMiddleware,
    TodoListMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from langgraph.store.postgres import PostgresStore
from langgraph.types import Command, interrupt


def _major_version(distribution: str) -> int:
    return int(version(distribution).split(".", maxsplit=1)[0])


def test_locked_langchain_and_langgraph_major_versions_match_v1_api() -> None:
    assert _major_version("langchain") == 1
    assert _major_version("langgraph") == 1
    assert _major_version("langgraph-checkpoint-postgres") == 3
    assert _major_version("pydantic") == 2


def test_phase_four_and_future_agent_public_apis_are_available() -> None:
    public_apis: tuple[Any, ...] = (
        create_agent,
        StateGraph,
        Runtime,
        Command,
        interrupt,
        PostgresSaver,
        PostgresStore,
        SummarizationMiddleware,
        TodoListMiddleware,
        HumanInTheLoopMiddleware,
        ModelCallLimitMiddleware,
        ToolCallLimitMiddleware,
        ToolRetryMiddleware,
        ModelRetryMiddleware,
        ModelFallbackMiddleware,
    )

    assert all(api is not None for api in public_apis)
    assert hasattr(PostgresSaver, "from_conn_string")
    assert hasattr(PostgresSaver, "setup")
    assert hasattr(PostgresStore, "from_conn_string")
    assert hasattr(PostgresStore, "setup")

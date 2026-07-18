from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from langchain_core.runnables import RunnableConfig

from apps.agents.configuration import get_agent_config


@dataclass(frozen=True, slots=True)
class GraphExecutionLimits:
    recursion_limit: int
    max_concurrency: int

    def __post_init__(self) -> None:
        if self.recursion_limit < 1:
            raise ValueError("recursion_limit must be positive")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")

    def apply(self, config: RunnableConfig) -> RunnableConfig:
        return {
            **config,
            "recursion_limit": self.recursion_limit,
            "max_concurrency": self.max_concurrency,
        }


class GraphStepLimitExceededError(RuntimeError):
    def __init__(self, recursion_limit: int) -> None:
        self.recursion_limit = recursion_limit
        super().__init__(f"Graph stopped after reaching the {recursion_limit}-step execution limit")


def get_graph_execution_limits() -> GraphExecutionLimits:
    try:
        graph = get_agent_config().graph
        return GraphExecutionLimits(
            recursion_limit=int(graph.recursion_limit),
            max_concurrency=int(graph.max_concurrency),
        )
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured("Invalid LangGraph execution limit settings") from exc

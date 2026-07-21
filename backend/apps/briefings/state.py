import operator
from typing import Annotated

from langchain.agents import AgentState

from apps.briefings.schemas import BriefingAgentReport, ResearchToolResult


class BriefingAgentState(AgentState[BriefingAgentReport]):
    """Ephemeral state for one Briefing Agent invocation.

    The state is deliberately not checkpointed. Durable evidence is copied to
    BriefingRun after the agent finishes.
    """

    research_results: Annotated[list[ResearchToolResult], operator.add]
    attempted_sections: list[str]
    repair_mode: bool

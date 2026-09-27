from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from langchain.agents.middleware import ToolCallRequest
from langchain.agents.middleware.human_in_the_loop import InterruptOnConfig

from apps.agents.tool_metadata import HITL_POLICY_METADATA

DecisionType = Literal["approve", "edit", "reject"]


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    risk_level: Literal["high"]
    allowed_decisions: tuple[DecisionType, ...]
    description: str


HIGH_RISK_TOOL_POLICIES: dict[str, RiskPolicy] = {
    name: RiskPolicy(
        risk_level="high",
        allowed_decisions=decisions,  # type: ignore[arg-type]
        description=description,
    )
    for name, (decisions, description) in HITL_POLICY_METADATA.items()
}


def policy_for_tool(tool_name: str) -> RiskPolicy | None:
    return HIGH_RISK_TOOL_POLICIES.get(tool_name)


def hitl_interrupt_policy(
    *,
    when: Callable[[str], Callable[[ToolCallRequest], bool]] | None = None,
) -> dict[str, bool | InterruptOnConfig]:
    policies: dict[str, bool | InterruptOnConfig] = {}
    for name, policy in HIGH_RISK_TOOL_POLICIES.items():
        config: InterruptOnConfig = {
            "allowed_decisions": list(policy.allowed_decisions),
            "description": policy.description,
        }
        if when is not None:
            config["when"] = when(name)
        policies[name] = config
    return policies

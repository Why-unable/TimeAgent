from dataclasses import dataclass
from typing import Literal

from langchain.agents.middleware.human_in_the_loop import InterruptOnConfig

DecisionType = Literal["approve", "edit", "reject"]


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    risk_level: Literal["high"]
    allowed_decisions: tuple[DecisionType, ...]
    description: str


HIGH_RISK_TOOL_POLICIES: dict[str, RiskPolicy] = {
    "create_event": RiskPolicy(
        risk_level="high",
        allowed_decisions=("approve", "edit", "reject"),
        description="创建正式日程会占用你的日历时间，需要确认后执行。",
    ),
    "cancel_event": RiskPolicy(
        risk_level="high",
        allowed_decisions=("approve", "reject"),
        description="取消日程会移除既有日历占用，需要确认后执行。",
    ),
    "cancel_reminder": RiskPolicy(
        risk_level="high",
        allowed_decisions=("approve", "reject"),
        description="取消提醒后将不会再按计划通知，需要确认后执行。",
    ),
    "cancel_task": RiskPolicy(
        risk_level="high",
        allowed_decisions=("approve", "reject"),
        description="取消任务会终止其后续执行计划，需要确认后执行。",
    ),
}


def policy_for_tool(tool_name: str) -> RiskPolicy | None:
    return HIGH_RISK_TOOL_POLICIES.get(tool_name)


def hitl_interrupt_policy() -> dict[str, bool | InterruptOnConfig]:
    return {
        name: InterruptOnConfig(
            allowed_decisions=list(policy.allowed_decisions),
            description=policy.description,
        )
        for name, policy in HIGH_RISK_TOOL_POLICIES.items()
    }

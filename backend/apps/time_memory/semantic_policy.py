import json
import re

from apps.time_memory.semantic_schemas import MemoryPolicyDecision, MemoryProposalPayload

_ALLOWED_CATEGORIES = frozenset(
    {
        "scheduling_preference",
        "availability_constraint",
        "location_preference",
        "notification_preference",
    }
)
_SENSITIVE_PATTERN = re.compile(
    r"(?:api[_ -]?key|token|password|secret|cookie|身份证|银行卡|病史|宗教|政治)",
    re.IGNORECASE,
)
_PROMPT_INJECTION_PATTERN = re.compile(
    r"(?:ignore|disregard).{0,24}(?:previous|above|system|instruction)"
    r"|(?:system\s*prompt|developer\s*message|tool\s*(?:output|result))"
    r"|(?:忽略|无视).{0,16}(?:之前|以上|系统|指令|规则)"
    r"|(?:系统提示|开发者消息|工具输出|工具结果)",
    re.IGNORECASE,
)
_DIRECT_APPLY_CATEGORIES = frozenset(
    {"scheduling_preference", "location_preference", "notification_preference"}
)


class MemoryPolicy:
    """Deterministic gate between model proposals and persistent memory."""

    MIN_CONFIDENCE = 0.75

    @classmethod
    def evaluate(
        cls,
        proposal: MemoryProposalPayload,
        *,
        explicit_user_authorized: bool = False,
        direct_apply_mode: str = "confirm",
    ) -> MemoryPolicyDecision:
        if proposal.category not in _ALLOWED_CATEGORIES:
            return MemoryPolicyDecision(
                action="reject",
                reason_code="category_not_allowed",
                reason="category is not allowed",
            )
        value_text = json.dumps(proposal.value, ensure_ascii=False, sort_keys=True)
        if any(
            _SENSITIVE_PATTERN.search(text)
            for text in (proposal.evidence_excerpt, proposal.key, value_text)
        ):
            return MemoryPolicyDecision(
                action="reject", reason_code="sensitive_content", reason="sensitive content"
            )
        if any(
            _PROMPT_INJECTION_PATTERN.search(text)
            for text in (proposal.evidence_excerpt, proposal.key, value_text)
        ):
            return MemoryPolicyDecision(
                action="reject",
                reason_code="prompt_injection_content",
                reason="instruction-like content cannot become memory",
            )
        if proposal.operation == "ignore":
            return MemoryPolicyDecision(
                action="reject", reason_code="ignored", reason="not a memory"
            )
        if proposal.confidence < cls.MIN_CONFIDENCE:
            return MemoryPolicyDecision(
                action="reject", reason_code="low_confidence", reason="confidence below threshold"
            )
        if proposal.category == "availability_constraint":
            return MemoryPolicyDecision(
                action="require_confirmation",
                reason_code="user_confirmation_required",
                reason="this change affects future planning",
            )
        direct_candidate = (
            explicit_user_authorized
            and proposal.category in _DIRECT_APPLY_CATEGORIES
            and proposal.operation in {"create", "update", "delete"}
        )
        if direct_candidate and direct_apply_mode == "enabled":
            return MemoryPolicyDecision(
                action="apply",
                reason_code="explicit_low_risk_direct_apply",
                reason="explicit low-risk memory command",
            )
        if direct_candidate and direct_apply_mode == "shadow":
            return MemoryPolicyDecision(
                action="require_confirmation",
                reason_code="shadow_direct_apply_candidate",
                reason="direct apply candidate retained for confirmation",
            )
        return MemoryPolicyDecision(
            action="require_confirmation", reason_code="explicit_confirmation"
        )

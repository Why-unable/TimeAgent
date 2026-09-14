from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SemanticMemoryOperation = Literal["create", "update", "delete", "ignore"]
SemanticMemoryCategory = Literal[
    "scheduling_preference",
    "availability_constraint",
    "location_preference",
    "notification_preference",
]


class MemoryProposalPayload(BaseModel):
    """Strict, bounded output expected from a future extraction model."""

    model_config = ConfigDict(extra="forbid")

    operation: SemanticMemoryOperation
    category: SemanticMemoryCategory
    key: str = Field(min_length=1, max_length=128)
    value: dict[str, object] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    evidence_excerpt: str = Field(min_length=1, max_length=1000)
    reason_code: str = Field(min_length=1, max_length=64)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        normalized = "_".join(value.strip().casefold().split())
        if not normalized:
            raise ValueError("key cannot be blank")
        return normalized


class MemoryPolicyDecision(BaseModel):
    action: Literal["apply", "require_confirmation", "reject"]
    reason_code: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=128)

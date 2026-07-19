import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

CURRENT_CONFIG_VERSION = 1
ENV_REFERENCE = re.compile(
    r"^\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|"
    r"(?P<plain>[A-Za-z_][A-Za-z0-9_]*))$"
)


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelDefinition(StrictConfigModel):
    provider: Literal["openai_compatible", "anthropic"] = "openai_compatible"
    model: str
    api_key: SecretStr = SecretStr("")
    base_url: str | None = None
    timeout_seconds: float = Field(default=120, gt=0)
    provider_max_retries: int = Field(default=0, ge=0)
    temperature: float = Field(default=0, ge=0, le=2)
    streaming: bool = True
    stream_usage: bool | None = None
    max_completion_tokens: int | None = Field(default=None, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    extra_body: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("model cannot be empty")
        return normalized

    @field_validator("base_url", mode="before")
    @classmethod
    def normalize_base_url(cls, value: Any) -> Any:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_provider_options(self) -> Self:
        if self.provider == "anthropic":
            if self.max_completion_tokens is not None:
                raise ValueError("anthropic models use max_tokens, not max_completion_tokens")
            if self.reasoning_effort is not None:
                raise ValueError("anthropic models do not support reasoning_effort")
            if self.extra_body:
                raise ValueError("anthropic models do not accept extra_body")
            if self.base_url and self.base_url.rstrip("/").endswith("/v1"):
                raise ValueError("anthropic base_url should be the API root without a trailing /v1")
        if self.provider == "openai_compatible" and self.max_tokens is not None:
            raise ValueError(
                "openai_compatible models use max_completion_tokens or extra_body, not max_tokens"
            )
        return self


class AgentDefinition(StrictConfigModel):
    default_model: str
    fallback_models: list[str] = Field(default_factory=list)
    briefing_editor_model: str | None = None


class GraphDefinition(StrictConfigModel):
    recursion_limit: int = Field(default=50, ge=1)
    max_concurrency: int = Field(default=4, ge=1)


class SummarizationDefinition(StrictConfigModel):
    enabled: bool = True
    trigger_messages: int = Field(default=24, ge=2)
    keep_messages: int = Field(default=12, ge=1)

    @model_validator(mode="after")
    def validate_retention(self) -> Self:
        if self.keep_messages >= self.trigger_messages:
            raise ValueError("keep_messages must be lower than trigger_messages")
        return self


class MiddlewareDefinition(StrictConfigModel):
    model_call_limit: int = Field(default=8, ge=1)
    tool_call_limit: int = Field(default=16, ge=1)
    model_retry_limit: int = Field(default=2, ge=0)
    tool_retry_limit: int = Field(default=2, ge=0)
    summarization: SummarizationDefinition = Field(default_factory=SummarizationDefinition)


class TimeAgentConfig(StrictConfigModel):
    config_version: int
    agent: AgentDefinition
    models: dict[str, ModelDefinition]
    graph: GraphDefinition = Field(default_factory=GraphDefinition)
    middleware: MiddlewareDefinition = Field(default_factory=MiddlewareDefinition)

    @field_validator("config_version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value != CURRENT_CONFIG_VERSION:
            raise ValueError(
                f"Unsupported config_version {value}; expected {CURRENT_CONFIG_VERSION}"
            )
        return value

    @model_validator(mode="after")
    def validate_default_model(self) -> Self:
        if self.agent.default_model not in self.models:
            raise ValueError("agent.default_model must reference a configured model alias")
        if len(self.agent.fallback_models) != len(set(self.agent.fallback_models)):
            raise ValueError("agent.fallback_models must not contain duplicates")
        if self.agent.default_model in self.agent.fallback_models:
            raise ValueError("agent.fallback_models must not contain agent.default_model")
        unknown_fallbacks = set(self.agent.fallback_models) - set(self.models)
        if unknown_fallbacks:
            names = ", ".join(sorted(unknown_fallbacks))
            raise ValueError(f"agent.fallback_models reference unknown model aliases: {names}")
        if (
            self.agent.briefing_editor_model is not None
            and self.agent.briefing_editor_model not in self.models
        ):
            raise ValueError("agent.briefing_editor_model must reference a configured model alias")
        return self

    def selected_model(self, name: str | None = None) -> ModelDefinition:
        selected_name = (name or self.agent.default_model).strip()
        try:
            return self.models[selected_name]
        except KeyError as exc:
            raise ImproperlyConfigured(
                f"Agent model alias is not configured: {selected_name}"
            ) from exc


def default_config_path() -> Path:
    configured = os.getenv("TIME_AGENT_CONFIG_PATH", "").strip()
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else Path(settings.BASE_DIR) / path
    return Path(settings.BASE_DIR) / "config" / "agent.example.yaml"


def load_agent_config(path: str | Path | None = None) -> TimeAgentConfig:
    config_path = Path(path) if path is not None else default_config_path()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ImproperlyConfigured(f"Cannot read Agent config: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ImproperlyConfigured(f"Invalid Agent YAML: {config_path}") from exc
    if not isinstance(raw, dict):
        raise ImproperlyConfigured("Agent config root must be a mapping")
    try:
        return TimeAgentConfig.model_validate(_expand_environment(raw))
    except ValidationError as exc:
        raise ImproperlyConfigured(f"Invalid Agent config: {exc}") from exc


@lru_cache(maxsize=1)
def get_agent_config() -> TimeAgentConfig:
    """Load and validate the process-wide restart-required Agent configuration."""

    return load_agent_config()


def _expand_environment(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_environment(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_environment(item) for item in value]
    if isinstance(value, str):
        match = ENV_REFERENCE.fullmatch(value)
        if match:
            return os.getenv(match.group("braced") or match.group("plain") or "", "")
    return value

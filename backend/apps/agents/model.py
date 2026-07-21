from typing import Any

from django.core.exceptions import ImproperlyConfigured
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from apps.agents.configuration import get_agent_config


def build_chat_model(model_name: str | None = None) -> BaseChatModel:
    definition = get_agent_config().selected_model(model_name)
    api_key = definition.api_key.get_secret_value().strip()
    if not api_key:
        raise ImproperlyConfigured("The selected Agent model requires a non-empty API key")
    common_kwargs: dict[str, Any] = {
        "model": definition.model,
        "api_key": SecretStr(api_key),
        "base_url": definition.base_url,
        "timeout": definition.timeout_seconds,
        "temperature": definition.temperature,
        "max_retries": definition.provider_max_retries,
        "streaming": definition.streaming,
    }
    if definition.stream_usage is not None:
        common_kwargs["stream_usage"] = definition.stream_usage
    if definition.provider == "openai_compatible":
        extra_body = dict(definition.extra_body)
        if definition.enable_thinking is not None:
            # DeepSeek's OpenAI-compatible protocol expects the provider-specific
            # thinking toggle in extra_body, not as a top-level LangChain option.
            extra_body["thinking"] = {
                "type": "enabled" if definition.enable_thinking else "disabled"
            }
        model = init_chat_model(
            **common_kwargs,
            model_provider="openai",
            max_completion_tokens=definition.max_completion_tokens,
            reasoning_effort=definition.reasoning_effort,
            extra_body=extra_body or None,
        )
    elif definition.provider == "anthropic":
        model = init_chat_model(
            **common_kwargs,
            model_provider="anthropic",
            max_tokens=definition.max_tokens,
        )
    else:
        raise ImproperlyConfigured(f"Unsupported Agent model provider: {definition.provider}")
    if not isinstance(model, BaseChatModel):
        raise ImproperlyConfigured("The selected Agent model did not initialize a chat model")
    return model


def build_fallback_chat_models() -> list[BaseChatModel]:
    """Build configured fallback models in failover order."""

    config = get_agent_config()
    return [build_chat_model(alias) for alias in config.agent.fallback_models]

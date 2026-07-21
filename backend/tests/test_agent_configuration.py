from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from langchain_core.language_models.chat_models import BaseChatModel

from apps.agents.configuration import get_agent_config, load_agent_config
from apps.agents.model import build_chat_model, build_fallback_chat_models


def write_config(
    path: Path,
    *,
    version: int = 1,
    default_model: str = "primary",
    fallback_models: str = "[]",
    extra_models: str = "",
) -> None:
    path.write_text(
        f"""
config_version: {version}
agent:
  default_model: {default_model}
  fallback_models: {fallback_models}
models:
  primary:
    provider: openai_compatible
    model: test-model
    api_key: $TEST_AGENT_API_KEY
    base_url: $TEST_AGENT_BASE_URL
{extra_models}
graph:
  recursion_limit: 21
  max_concurrency: 3
middleware:
  model_call_limit: 5
  tool_call_limit: 9
  model_retry_limit: 1
  tool_retry_limit: 0
  summarization:
    enabled: true
    trigger_messages: 10
    keep_messages: 4
""".strip(),
        encoding="utf-8",
    )


def test_yaml_config_expands_secret_environment_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "agent.yaml"
    write_config(path)
    monkeypatch.setenv("TEST_AGENT_API_KEY", "secret-value")
    monkeypatch.setenv("TEST_AGENT_BASE_URL", "https://models.example/v1")

    config = load_agent_config(path)

    model = config.selected_model()
    assert model.model == "test-model"
    assert model.api_key.get_secret_value() == "secret-value"
    assert "secret-value" not in repr(config)
    assert model.base_url == "https://models.example/v1"
    assert config.graph.recursion_limit == 21
    assert config.middleware.summarization.keep_messages == 4


def test_invalid_version_and_unknown_default_model_fail_at_startup(tmp_path: Path) -> None:
    outdated = tmp_path / "outdated.yaml"
    write_config(outdated, version=999)
    with pytest.raises(ImproperlyConfigured, match="config_version"):
        load_agent_config(outdated)

    missing_model = tmp_path / "missing-model.yaml"
    write_config(missing_model, default_model="missing")
    with pytest.raises(ImproperlyConfigured, match="default_model"):
        load_agent_config(missing_model)

    missing_fallback = tmp_path / "missing-fallback.yaml"
    write_config(missing_fallback, fallback_models="[missing]")
    with pytest.raises(ImproperlyConfigured, match="fallback_models"):
        load_agent_config(missing_fallback)


def test_model_factory_uses_selected_validated_definition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "agent.yaml"
    write_config(path)
    monkeypatch.setenv("TEST_AGENT_API_KEY", "secret-value")
    monkeypatch.setenv("TEST_AGENT_BASE_URL", "https://models.example/v1")
    monkeypatch.setenv("TIME_AGENT_CONFIG_PATH", str(path))
    get_agent_config.cache_clear()
    try:
        with patch("apps.agents.model.init_chat_model") as init_model:
            init_model.return_value = MagicMock(spec=BaseChatModel)
            build_chat_model()
        kwargs = init_model.call_args.kwargs
        assert kwargs["model"] == "test-model"
        assert kwargs["model_provider"] == "openai"
        assert kwargs["base_url"] == "https://models.example/v1"
        assert kwargs["timeout"] == 120
        assert kwargs["max_retries"] == 0
        assert kwargs["api_key"].get_secret_value() == "secret-value"
    finally:
        get_agent_config.cache_clear()


def test_model_factory_uses_anthropic_provider_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "agent.yaml"
    write_config(
        path,
        default_model="claude",
        extra_models="""
  claude:
    provider: anthropic
    model: claude-test
    api_key: $TEST_AGENT_API_KEY
    base_url: $TEST_AGENT_BASE_URL
    stream_usage: false
    max_tokens: 2048
""",
    )
    monkeypatch.setenv("TEST_AGENT_API_KEY", "secret-value")
    monkeypatch.setenv("TEST_AGENT_BASE_URL", "https://anthropic.example")
    monkeypatch.setenv("TIME_AGENT_CONFIG_PATH", str(path))
    get_agent_config.cache_clear()
    try:
        with patch("apps.agents.model.init_chat_model") as init_model:
            init_model.return_value = MagicMock(spec=BaseChatModel)
            build_chat_model()
        kwargs = init_model.call_args.kwargs
        assert kwargs["model"] == "claude-test"
        assert kwargs["model_provider"] == "anthropic"
        assert kwargs["base_url"] == "https://anthropic.example"
        assert kwargs["stream_usage"] is False
        assert kwargs["max_tokens"] == 2048
        assert "extra_body" not in kwargs
        assert "max_completion_tokens" not in kwargs
    finally:
        get_agent_config.cache_clear()


def test_model_factory_maps_thinking_toggle_to_provider_extra_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "agent.yaml"
    write_config(
        path,
        default_model="deepseek",
        extra_models="""
  deepseek:
    provider: openai_compatible
    model: deepseek-v4-flash
    api_key: $TEST_AGENT_API_KEY
    base_url: https://api.deepseek.com
    enable_thinking: false
""",
    )
    monkeypatch.setenv("TEST_AGENT_API_KEY", "secret-value")
    monkeypatch.setenv("TIME_AGENT_CONFIG_PATH", str(path))
    get_agent_config.cache_clear()
    try:
        with patch("apps.agents.model.init_chat_model") as init_model:
            init_model.return_value = MagicMock(spec=BaseChatModel)
            build_chat_model()
        assert init_model.call_args.kwargs["extra_body"] == {
            "thinking": {"type": "disabled"}
        }
    finally:
        get_agent_config.cache_clear()


def test_model_config_can_select_tool_structured_output_for_relay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "agent.yaml"
    write_config(
        path,
        default_model="claude",
        extra_models="""
  claude:
    provider: anthropic
    model: claude-opus-4-6
    api_key: $TEST_AGENT_API_KEY
    base_url: https://relay.example
    max_tokens: 2048
    structured_output_strategy: tool
""",
    )
    monkeypatch.setenv("TEST_AGENT_API_KEY", "secret-value")

    config = load_agent_config(path)

    assert config.selected_model("claude").structured_output_strategy == "tool"


def test_model_factory_builds_fallbacks_in_configured_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "agent.yaml"
    write_config(
        path,
        fallback_models="[secondary, tertiary]",
        extra_models="""
  secondary:
    provider: openai_compatible
    model: secondary-model
    api_key: $TEST_AGENT_API_KEY
  tertiary:
    provider: anthropic
    model: tertiary-model
    api_key: $TEST_AGENT_API_KEY
    max_tokens: 256
""",
    )
    monkeypatch.setenv("TEST_AGENT_API_KEY", "secret-value")
    monkeypatch.setenv("TIME_AGENT_CONFIG_PATH", str(path))
    get_agent_config.cache_clear()
    try:
        with patch("apps.agents.model.init_chat_model") as init_model:
            init_model.side_effect = [
                MagicMock(spec=BaseChatModel),
                MagicMock(spec=BaseChatModel),
            ]
            models = build_fallback_chat_models()
        assert len(models) == 2
        assert [call.kwargs["model"] for call in init_model.call_args_list] == [
            "secondary-model",
            "tertiary-model",
        ]
    finally:
        get_agent_config.cache_clear()


def test_provider_specific_model_options_are_validated(tmp_path: Path) -> None:
    path = tmp_path / "agent.yaml"
    write_config(
        path,
        default_model="claude",
        extra_models="""
  claude:
    provider: anthropic
    model: claude-test
    api_key: $TEST_AGENT_API_KEY
    base_url: https://anthropic.example/v1
    max_completion_tokens: 10
""",
    )

    with pytest.raises(ImproperlyConfigured, match="anthropic"):
        load_agent_config(path)

    conflicting = tmp_path / "conflicting-thinking.yaml"
    write_config(
        conflicting,
        extra_models="""
  deepseek:
    provider: openai_compatible
    model: deepseek-v4-flash
    api_key: $TEST_AGENT_API_KEY
    enable_thinking: false
    extra_body:
      thinking:
        type: disabled
""",
    )
    with pytest.raises(ImproperlyConfigured, match="enable_thinking"):
        load_agent_config(conflicting)

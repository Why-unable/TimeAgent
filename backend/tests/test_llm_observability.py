from types import SimpleNamespace
from typing import Any

import pytest
from langchain.agents.middleware import ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from apps.observability.llm_middleware import LLMUsageMiddleware
from apps.observability.models import LLMCallAudit

pytestmark = pytest.mark.django_db


class TokenCountingModel:
    model_name = "test-model"

    @staticmethod
    def get_num_tokens(text: str) -> int:
        return 12 if text else 0

    @staticmethod
    def get_num_tokens_from_messages(
        messages: list[BaseMessage], tools: Any = None
    ) -> int:
        del messages, tools
        return 100


def request_with_memory() -> Any:
    return SimpleNamespace(
        model=TokenCountingModel(),
        messages=[HumanMessage(content="安排一下明天")],
        system_message=SystemMessage(
            content=(
                "系统提示\n<time_behavior_memory>\n- data=工作日早起\n"
                "</time_behavior_memory>"
            )
        ),
        tools=[],
        runtime=SimpleNamespace(
            context=SimpleNamespace(request_id="request-token-1", agent_run_id="run-token-1")
        ),
    )


def test_llm_usage_middleware_records_provider_tokens_and_memory_ratio() -> None:
    middleware = LLMUsageMiddleware("time_steward", track_memory=True)
    response = ModelResponse(
        result=[
            AIMessage(
                content="好的",
                usage_metadata={"input_tokens": 200, "output_tokens": 20, "total_tokens": 220},
            )
        ]
    )

    returned = middleware.wrap_model_call(request_with_memory(), lambda request: response)

    assert returned is response
    audit = LLMCallAudit.objects.get()
    assert audit.request_id == "request-token-1"
    assert audit.component == "time_steward"
    assert audit.model_name == "test-model"
    assert audit.usage_source == "provider"
    assert audit.input_tokens == 200
    assert audit.output_tokens == 20
    assert audit.total_tokens == 220
    assert audit.memory_prompt_tokens == 12
    assert audit.memory_prompt_ratio == pytest.approx(0.06)


def test_llm_usage_middleware_estimates_usage_without_provider_metadata() -> None:
    middleware = LLMUsageMiddleware("briefing_agent")
    response = ModelResponse(result=[AIMessage(content="简报完成")])

    middleware.wrap_model_call(request_with_memory(), lambda request: response)

    audit = LLMCallAudit.objects.get()
    assert audit.usage_source == "estimated"
    assert audit.input_tokens == 100
    assert audit.output_tokens == 12
    assert audit.total_tokens == 112
    assert audit.memory_prompt_tokens == 0
    assert audit.memory_prompt_ratio == 0

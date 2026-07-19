import json
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ModelRetryMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable

from apps.agents.configuration import get_agent_config
from apps.agents.model import build_chat_model
from apps.briefings.schemas import BriefingDraft, SectionResult

PROMPT_VERSION = "briefing-editor-v2-weather-news"
PROMPT_PATH = Path(__file__).with_name("prompts") / "editor.md"
EDITOR_SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_briefing_editor_agent(*, model: BaseChatModel | None = None) -> Runnable[Any, Any]:
    config = get_agent_config()
    model_alias = config.agent.briefing_editor_model or config.agent.default_model
    resolved_model = model or build_chat_model(model_alias)
    middleware: list[Any] = [
        ModelCallLimitMiddleware(run_limit=2, exit_behavior="end"),
        ModelRetryMiddleware(max_retries=1, on_failure="error"),
    ]
    return create_agent(
        model=resolved_model,
        tools=[],
        system_prompt=EDITOR_SYSTEM_PROMPT,
        response_format=ToolStrategy(BriefingDraft),
        middleware=middleware,
        name="briefing_editor",
    )


def edit_briefing(
    *,
    sections: list[SectionResult],
    target_date: str,
    timezone: str,
    locale: str,
    style: str,
    request_text: str,
    editor: Runnable[Any, Any] | None = None,
) -> BriefingDraft:
    payload = {
        "target_date": target_date,
        "timezone": timezone,
        "locale": locale,
        "style": style,
        "request": request_text,
        "sections": [item.model_dump(mode="json") for item in sections],
    }
    result = (editor or build_briefing_editor_agent()).invoke(
        {"messages": [HumanMessage(content=json.dumps(payload, ensure_ascii=False))]}
    )
    draft = result.get("structured_response") if isinstance(result, dict) else None
    if not isinstance(draft, BriefingDraft):
        raise RuntimeError("Briefing Editor did not return a structured response")
    return draft


def editor_model_snapshot() -> dict[str, Any]:
    config = get_agent_config()
    alias = config.agent.briefing_editor_model or config.agent.default_model
    definition = config.selected_model(alias)
    return {"alias": alias, "provider": definition.provider, "model": definition.model}

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.context import RuntimeContext
from apps.agents.model import build_chat_model
from apps.preferences.services import UserPreferenceService

EVAL_NOW = datetime(2026, 7, 17, 8, tzinfo=UTC)
EVAL_TIMEZONE = "Asia/Shanghai"
EVAL_LOCALE = "zh-CN"


class Command(BaseCommand):
    help = "Run the fixed Time Steward trajectory evaluation against a real configured model."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--model",
            help="Configured model alias; defaults to agent.default_model.",
        )
        parser.add_argument(
            "--case",
            action="append",
            dest="case_ids",
            help="Run only the selected case ID. May be repeated.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        cases = self._load_cases()
        selected = set(options.get("case_ids") or [])
        if selected:
            known = {case["id"] for case in cases}
            unknown = selected - known
            if unknown:
                raise CommandError(f"Unknown eval case(s): {', '.join(sorted(unknown))}")
            cases = [case for case in cases if case["id"] in selected]

        model_alias = options.get("model")
        model = build_chat_model(model_alias)
        agent = build_time_steward_agent(model=model)
        failures: list[str] = []

        # Eval write tools exercise real Application Services, but every business
        # mutation is rolled back so the fixed suite never changes authoritative data.
        with transaction.atomic():
            user = User.objects.create_user(username=f"agent-eval-{uuid4().hex}")
            UserPreferenceService.update_for_user(
                user,
                {"timezone": EVAL_TIMEZONE, "locale": EVAL_LOCALE},
            )
            for case in cases:
                actual = self._run_case(agent, user, case)
                required = set(case["required_tools"])
                allowed = set(case["allowed_tools"])
                forbidden = set(case["forbidden_tools"])
                missing = required - actual
                unexpected = actual - allowed
                forbidden_used = forbidden & actual
                passed = not missing and not unexpected and not forbidden_used
                self.stdout.write(
                    json.dumps(
                        {
                            "id": case["id"],
                            "passed": passed,
                            "actual_tools": sorted(actual),
                            "missing_tools": sorted(missing),
                            "unexpected_tools": sorted(unexpected),
                            "forbidden_tools_used": sorted(forbidden_used),
                        },
                        ensure_ascii=False,
                    )
                )
                if not passed:
                    failures.append(case["id"])
            transaction.set_rollback(True)

        if failures:
            raise CommandError(f"Time Steward eval failed: {', '.join(failures)}")
        self.stdout.write(self.style.SUCCESS(f"Time Steward eval passed: {len(cases)} case(s)"))

    @staticmethod
    def _run_case(agent: Any, user: User, case: dict[str, Any]) -> set[str]:
        conversation_id = str(uuid4())
        context = RuntimeContext(
            user_id=str(user.pk),
            request_id=str(uuid4()),
            timezone=EVAL_TIMEZONE,
            locale=EVAL_LOCALE,
            current_datetime=EVAL_NOW,
            trigger_type="user_message",
            conversation_id=conversation_id,
            read_only=False,
            actor=user,
        )
        result = agent.invoke(
            {"messages": [HumanMessage(content=case["prompt"])]},
            context=context,
        )
        messages = result.get("messages", [])
        if not messages or not isinstance(messages[-1], AIMessage):
            raise CommandError(f"Eval case {case['id']} did not produce a final AIMessage")
        return {
            str(tool_call["name"])
            for message in messages
            if isinstance(message, AIMessage)
            for tool_call in message.tool_calls
        }

    @staticmethod
    def _load_cases() -> list[dict[str, Any]]:
        path = Path(settings.BASE_DIR) / "tests" / "fixtures" / "time_steward_eval.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot load fixed eval set: {path}") from exc
        if not isinstance(value, list) or not value:
            raise CommandError("Fixed eval set must be a non-empty list")
        return value

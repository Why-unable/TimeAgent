from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.briefings.models import (
    BriefingDefinition,
    BriefingRun,
    BriefingRunStatus,
    BriefingSectionRun,
    BriefingSectionStatus,
)
from apps.briefings.schemas import (
    BRIEFING_SECTION_KEYS,
    BriefingAgentReport,
    BriefingResult,
    BriefingSectionKey,
    SectionResult,
)
from apps.conversations.models import AgentRun, Conversation
from common.time import validate_timezone


@dataclass(frozen=True, slots=True)
class StartBriefingCommand:
    user: User
    operation_id: UUID
    trigger_type: str
    target_date: date
    timezone: str = ""
    definition_id: UUID | None = None
    conversation: Conversation | None = None
    agent_run: AgentRun | None = None
    requested_sections: list[BriefingSectionKey] | None = None


class BriefingDefinitionService:
    @staticmethod
    def default_for_user(user: User) -> BriefingDefinition:
        definition, _ = BriefingDefinition.objects.get_or_create(
            user=user,
            name="每日简报",
            defaults={"enabled_sections": ["calendar", "tasks", "weather", "news"]},
        )
        return definition

    @staticmethod
    def get(*, user: User, definition_id: UUID) -> BriefingDefinition:
        return BriefingDefinition.objects.get(pk=definition_id, user=user)

    @staticmethod
    def list_definitions(*, user: User) -> list[BriefingDefinition]:
        return list(BriefingDefinition.objects.filter(user=user))

    @staticmethod
    def save(
        *,
        user: User,
        name: str,
        enabled_sections: list[str],
        locale: str = "",
        timezone_name: str = "",
        style: str = "balanced",
        include_empty_sections: bool = False,
        definition: BriefingDefinition | None = None,
    ) -> BriefingDefinition:
        unknown: set[str] = set(enabled_sections) - BRIEFING_SECTION_KEYS
        if unknown:
            raise ValueError(f"Unknown briefing sections: {', '.join(sorted(unknown))}")
        if timezone_name:
            validate_timezone(timezone_name)
        item = definition or BriefingDefinition(user=user)
        if item.pk and item.user_id != user.pk:
            raise PermissionError("Briefing definition belongs to another user")
        item.name = name.strip()
        item.enabled_sections = enabled_sections
        item.locale = locale.strip()
        item.timezone = timezone_name.strip()
        item.style = style
        item.include_empty_sections = include_empty_sections
        item.full_clean()
        item.save()
        return item


class BriefingRunService:
    @staticmethod
    @transaction.atomic
    def start(command: StartBriefingCommand) -> BriefingRun:
        definition = (
            BriefingDefinitionService.get(user=command.user, definition_id=command.definition_id)
            if command.definition_id
            else BriefingDefinitionService.default_for_user(command.user)
        )
        timezone_name = definition.timezone or command.timezone or settings.DEFAULT_USER_TIMEZONE
        validate_timezone(timezone_name)
        section_keys = command.requested_sections or list(definition.enabled_sections)
        unknown = set(section_keys) - BRIEFING_SECTION_KEYS
        if unknown:
            raise ValueError(f"Unknown briefing sections: {', '.join(sorted(unknown))}")
        run, created = BriefingRun.objects.get_or_create(
            operation_id=command.operation_id,
            defaults={
                "definition": definition,
                "user": command.user,
                "conversation": command.conversation,
                "agent_run": command.agent_run,
                "trigger_type": command.trigger_type,
                "target_date": command.target_date,
                "timezone": timezone_name,
                "definition_snapshot": {
                    "id": str(definition.pk),
                    "name": definition.name,
                    "enabled_sections": definition.enabled_sections,
                    "requested_sections": section_keys,
                    "locale": definition.locale,
                    "timezone": timezone_name,
                    "style": definition.style,
                    "include_empty_sections": definition.include_empty_sections,
                },
            },
        )
        if run.user_id != command.user.pk or run.target_date != command.target_date:
            raise ValueError("operation_id already belongs to another briefing run")
        if created:
            BriefingSectionRun.objects.bulk_create(
                [BriefingSectionRun(briefing_run=run, section_key=key) for key in section_keys]
            )
        return run

    @staticmethod
    @transaction.atomic
    def mark_running(run: BriefingRun) -> BriefingRun:
        locked = BriefingRun.objects.select_for_update().get(pk=run.pk)
        if locked.status == BriefingRunStatus.PENDING:
            locked.status = BriefingRunStatus.RUNNING
            locked.started_at = timezone.now()
            locked.save(update_fields=["status", "started_at"])
        return locked

    @staticmethod
    @transaction.atomic
    def start_section(run: BriefingRun, section_key: str) -> None:
        BriefingSectionRun.objects.update_or_create(
            briefing_run=run,
            section_key=section_key,
            defaults={
                "status": BriefingSectionStatus.RUNNING,
                "started_at": timezone.now(),
            },
        )

    @staticmethod
    @transaction.atomic
    def finish_section(run: BriefingRun, result: SectionResult) -> None:
        # JSONField must receive JSON-native values. Research evidence may originate
        # from Django models and therefore contain UUID/date/enum objects even when
        # the corresponding ToolMessage artifact was already JSON-encoded.
        serialized_result = result.model_dump(mode="json")
        BriefingSectionRun.objects.filter(briefing_run=run, section_key=result.key).update(
            status=(
                BriefingSectionStatus.COMPLETED
                if result.status == "completed"
                else BriefingSectionStatus.FAILED
            ),
            source_snapshot=serialized_result["data"],
            source_references=serialized_result["sources"],
            warning="\n".join(result.warnings),
            error_code=result.error_code,
            completed_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def complete(
        run: BriefingRun,
        result: BriefingResult,
        *,
        agent_report: BriefingAgentReport | None = None,
        model_config_snapshot: dict[str, str] | None = None,
        prompt_version: str = "",
    ) -> BriefingRun:
        locked = BriefingRun.objects.select_for_update().get(pk=run.pk)
        locked.status = (
            BriefingRunStatus.PARTIAL if result.status == "partial" else BriefingRunStatus.COMPLETED
        )
        locked.structured_result = result.draft.model_dump(mode="json")
        locked.research_report = (
            agent_report.model_dump(mode="json") if agent_report is not None else {}
        )
        locked.rendered_markdown = result.markdown
        locked.warnings = result.warnings
        locked.model_config_snapshot = model_config_snapshot or {}
        locked.prompt_version = prompt_version
        locked.completed_at = timezone.now()
        locked.failure_code = ""
        locked.failure_message = ""
        locked.save(
            update_fields=[
                "status",
                "structured_result",
                "research_report",
                "rendered_markdown",
                "warnings",
                "model_config_snapshot",
                "prompt_version",
                "completed_at",
                "failure_code",
                "failure_message",
            ]
        )
        return locked

    @staticmethod
    @transaction.atomic
    def fail(run: BriefingRun, *, code: str, message: str) -> BriefingRun:
        locked = BriefingRun.objects.select_for_update().get(pk=run.pk)
        locked.status = BriefingRunStatus.FAILED
        locked.failure_code = code[:64]
        locked.failure_message = message[:4000]
        locked.completed_at = timezone.now()
        locked.save(update_fields=["status", "failure_code", "failure_message", "completed_at"])
        return locked

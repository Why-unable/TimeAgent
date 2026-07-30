from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from django.db import transaction

from apps.briefings.services import BriefingDefinitionService
from apps.conversations.models import AgentRun, ConversationKind
from apps.conversations.services import AgentRunService, ConversationService, StartRunCommand
from apps.preferences.models import UserPreference
from common.time import get_timezone, to_utc


@dataclass(frozen=True, slots=True)
class DueBriefing:
    preference_id: int
    target_date: date
    generation_at: datetime
    delivery_at: datetime


class DailyBriefingScheduler:
    GENERATION_LEAD = timedelta(minutes=5)
    CATCH_UP_WINDOW = timedelta(hours=1)

    @staticmethod
    def due(*, now: datetime) -> list[DueBriefing]:
        current = to_utc(now)
        due: list[DueBriefing] = []
        preferences = UserPreference.objects.select_related("user").filter(
            daily_briefing_enabled=True,
            user__is_active=True,
        )
        for preference in preferences.iterator():
            local_now = current.astimezone(get_timezone(preference.timezone))
            for day_offset in (0, 1):
                target_date = local_now.date() + timedelta(days=day_offset)
                local_delivery = datetime.combine(
                    target_date,
                    preference.briefing_time,
                    tzinfo=get_timezone(preference.timezone),
                )
                delivery_at = local_delivery.astimezone(UTC)
                generation_at = delivery_at - DailyBriefingScheduler.GENERATION_LEAD
                if generation_at <= current < delivery_at + DailyBriefingScheduler.CATCH_UP_WINDOW:
                    due.append(
                        DueBriefing(
                            preference_id=preference.pk,
                            target_date=target_date,
                            generation_at=generation_at,
                            delivery_at=delivery_at,
                        )
                    )
        return due

    @staticmethod
    @transaction.atomic
    def prepare(due: DueBriefing) -> tuple[AgentRun, bool]:
        preference = (
            UserPreference.objects.select_for_update()
            .select_related("user")
            .get(pk=due.preference_id)
        )
        operation_id = DailyBriefingScheduler.operation_id(
            user_id=preference.user_id,
            delivery_at=due.delivery_at,
        )
        existing = AgentRun.objects.filter(operation_id=operation_id).first()
        if existing is not None:
            return existing, False

        definition = BriefingDefinitionService.default_for_user(preference.user)
        title = f"{due.target_date.isoformat()} · 每日简报"
        message = f"自动生成 {due.target_date.isoformat()} 的每日简报"
        trigger_payload = {
            "briefing_definition_id": str(definition.pk),
            "target_date": due.target_date.isoformat(),
            "delivery_at": due.delivery_at.isoformat(),
            "request": "根据用户偏好生成每日简报，并在计划时间发送。",
        }
        conversation = ConversationService.create(
            user=preference.user,
            title=title,
            kind=ConversationKind.SCHEDULED_BRIEFING,
        )
        run = AgentRunService.start(
            StartRunCommand(
                conversation=conversation,
                operation_id=operation_id,
                request_id=f"scheduled-briefing-{uuid4()}",
                message=message,
                trigger_type="scheduled_briefing",
                trigger_payload=trigger_payload,
                synthetic_input=True,
            )
        )
        return run, True

    @staticmethod
    def operation_id(*, user_id: int, delivery_at: datetime) -> UUID:
        return uuid5(
            NAMESPACE_URL,
            f"time-agent:daily-briefing:{user_id}:{to_utc(delivery_at).isoformat()}",
        )

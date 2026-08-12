from collections import defaultdict
from collections.abc import Iterator
from datetime import timedelta
from statistics import median
from typing import Any

from django.db import OperationalError, ProgrammingError
from django.db.models import Count, F, Sum
from django.utils import timezone
from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily, Metric

_registered = False


def _quantile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * min(1.0, max(0.0, percentile))
    lower_index = int(position)
    upper_index = min(len(ordered) - 1, lower_index + 1)
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


class TimeAgentBusinessCollector:
    """Low-cardinality, database-backed business SLIs available from every web replica."""

    def describe(self):  # type: ignore[no-untyped-def]
        return []

    def collect(self) -> Iterator[Metric]:
        try:
            yield from self._collect()
        except (OperationalError, ProgrammingError):
            return

    def _collect(self) -> Iterator[Metric]:
        from apps.action_proposals.models import ActionProposal
        from apps.briefings.models import BriefingRun
        from apps.conversations.models import AgentRun, ToolCallAudit
        from apps.notifications.models import NotificationDelivery
        from apps.observability.models import LLMCallAudit

        now = timezone.now()
        since = now - timedelta(hours=24)

        runs = GaugeMetricFamily(
            "timeagent_agent_runs_24h",
            "Agent runs created in the last 24 hours.",
            labels=["status", "trigger_type"],
        )
        for row in (
            AgentRun.objects.filter(created_at__gte=since)
            .values("status", "trigger_type")
            .annotate(count=Count("id"))
        ):
            runs.add_metric([row["status"], row["trigger_type"]], row["count"])
        yield runs

        stale = GaugeMetricFamily(
            "timeagent_agent_runs_stale",
            "Agent runs pending or running longer than ten minutes.",
            labels=["status"],
        )
        stale_cutoff = now - timedelta(minutes=10)
        for status in ("pending", "running"):
            stale.add_metric(
                [status],
                AgentRun.objects.filter(status=status, created_at__lt=stale_cutoff).count(),
            )
        yield stale

        durations = list(
            AgentRun.objects.filter(
                completed_at__isnull=False,
                started_at__isnull=False,
                completed_at__gte=since,
            )
            .annotate(duration=F("completed_at") - F("started_at"))
            .values_list("duration", flat=True)
        )
        seconds = [max(0.0, value.total_seconds()) for value in durations if value is not None]
        run_duration = GaugeMetricFamily(
            "timeagent_agent_run_duration_seconds",
            "Observed agent run duration quantiles over the last 24 hours.",
            labels=["quantile"],
        )
        run_duration.add_metric(["0.5"], median(seconds) if seconds else 0.0)
        run_duration.add_metric(["0.95"], _quantile(seconds, 0.95))
        yield run_duration

        tools = GaugeMetricFamily(
            "timeagent_tool_calls_24h",
            "Tool calls started in the last 24 hours.",
            labels=["status", "tool_name"],
        )
        for row in (
            ToolCallAudit.objects.filter(started_at__gte=since)
            .values("status", "tool_name")
            .annotate(count=Count("id"))
        ):
            tools.add_metric([row["status"], row["tool_name"]], row["count"])
        yield tools

        briefings = GaugeMetricFamily(
            "timeagent_briefing_runs_24h",
            "Briefing workflow runs created in the last 24 hours.",
            labels=["status", "trigger_type"],
        )
        for row in (
            BriefingRun.objects.filter(created_at__gte=since)
            .values("status", "trigger_type")
            .annotate(count=Count("id"))
        ):
            briefings.add_metric([row["status"], row["trigger_type"]], row["count"])
        yield briefings

        deliveries = GaugeMetricFamily(
            "timeagent_notification_deliveries_24h",
            "Notification deliveries created in the last 24 hours.",
            labels=["status", "channel"],
        )
        for row in (
            NotificationDelivery.objects.filter(created_at__gte=since)
            .values("status", "channel_type")
            .annotate(count=Count("id"))
        ):
            deliveries.add_metric([row["status"], row["channel_type"]], row["count"])
        yield deliveries

        proposals = GaugeMetricFamily(
            "timeagent_action_proposals_current",
            "Current action proposals by state and risk level.",
            labels=["status", "risk_level"],
        )
        for row in ActionProposal.objects.values("status", "risk_level").annotate(
            count=Count("id")
        ):
            proposals.add_metric([row["status"], row["risk_level"]], row["count"])
        yield proposals

        llm_calls = GaugeMetricFamily(
            "timeagent_llm_calls_24h",
            "LLM calls completed in the last 24 hours.",
            labels=["component", "model", "status", "usage_source"],
        )
        for row in (
            LLMCallAudit.objects.filter(created_at__gte=since)
            .values("component", "model_name", "status", "usage_source")
            .annotate(count=Count("id"))
        ):
            llm_calls.add_metric(
                [row["component"], row["model_name"], row["status"], row["usage_source"]],
                row["count"],
            )
        yield llm_calls

        llm_tokens = GaugeMetricFamily(
            "timeagent_llm_tokens_24h",
            "LLM tokens consumed in the last 24 hours.",
            labels=["component", "model", "direction"],
        )
        for row in (
            LLMCallAudit.objects.filter(created_at__gte=since, status="completed")
            .values("component", "model_name")
            .annotate(
                input_total=Sum("input_tokens"),
                output_total=Sum("output_tokens"),
                combined_total=Sum("total_tokens"),
            )
        ):
            for direction, field in (
                ("input", "input_total"),
                ("output", "output_total"),
                ("total", "combined_total"),
            ):
                llm_tokens.add_metric(
                    [row["component"], row["model_name"], direction],
                    row[field] or 0,
                )
        yield llm_tokens

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for call_row in LLMCallAudit.objects.filter(
            created_at__gte=since,
            status="completed",
        ).values(
            "component",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "memory_prompt_tokens",
            "memory_prompt_ratio",
        ):
            grouped[str(call_row["component"])].append(dict(call_row))

        per_call_tokens = GaugeMetricFamily(
            "timeagent_llm_tokens_per_call_24h",
            "Observed LLM token quantiles per call over the last 24 hours.",
            labels=["component", "direction", "quantile"],
        )
        memory_tokens = GaugeMetricFamily(
            "timeagent_memory_prompt_tokens_per_call_24h",
            "Observed memory prompt token quantiles per LLM call over the last 24 hours.",
            labels=["component", "quantile"],
        )
        memory_ratio = GaugeMetricFamily(
            "timeagent_memory_prompt_ratio_24h",
            "Observed memory share of LLM input tokens over the last 24 hours.",
            labels=["component", "quantile"],
        )
        for component, rows in grouped.items():
            for direction, field in (
                ("input", "input_tokens"),
                ("output", "output_tokens"),
                ("total", "total_tokens"),
            ):
                values = [float(row[field]) for row in rows if row[field] is not None]
                for quantile, percentile in (("0.5", 0.5), ("0.95", 0.95)):
                    per_call_tokens.add_metric(
                        [component, direction, quantile],
                        _quantile(values, percentile),
                    )
            prompt_values = [float(row["memory_prompt_tokens"]) for row in rows]
            ratio_values = [
                float(row["memory_prompt_ratio"])
                for row in rows
                if row["memory_prompt_ratio"] is not None
            ]
            for quantile, percentile in (("0.5", 0.5), ("0.95", 0.95)):
                memory_tokens.add_metric(
                    [component, quantile],
                    _quantile(prompt_values, percentile),
                )
                memory_ratio.add_metric(
                    [component, quantile],
                    _quantile(ratio_values, percentile),
                )
        yield per_call_tokens
        yield memory_tokens
        yield memory_ratio


def register_business_collector() -> None:
    global _registered
    if _registered:
        return
    REGISTRY.register(TimeAgentBusinessCollector())
    _registered = True

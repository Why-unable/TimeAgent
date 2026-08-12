from apps.briefings.schemas import (
    BriefingAgendaItem,
    BriefingDraft,
    BriefingNewsItem,
    BriefingTaskItem,
    BriefingWeatherItem,
    SectionResult,
)


def validate_draft(draft: BriefingDraft, sections: list[SectionResult]) -> None:
    known_ids = {source.id for section in sections for source in section.sources}
    referenced_ids = {source_id for item in draft.agenda_items for source_id in item.source_ids}
    referenced_ids.update(source_id for item in draft.task_items for source_id in item.source_ids)
    referenced_ids.update(
        source_id for item in draft.weather_items for source_id in item.source_ids
    )
    referenced_ids.update(source_id for item in draft.news_items for source_id in item.source_ids)
    unknown = referenced_ids - known_ids
    if unknown:
        raise ValueError(f"Briefing output referenced unknown sources: {sorted(unknown)}")
    if any(not item.source_ids for item in draft.agenda_items):
        raise ValueError("Every briefing agenda item must reference a source")
    if any(not item.source_ids for item in draft.task_items):
        raise ValueError("Every briefing task item must reference a source")
    if any(not item.source_ids for item in draft.weather_items):
        raise ValueError("Every briefing weather item must reference a source")
    weather_section = next((item for item in sections if item.key == "weather"), None)
    if weather_section and weather_section.status == "completed":
        expected_weather_roles = {
            str(item.get("coordinate_role", ""))
            for item in weather_section.data.get("daily", [])
            if item.get("coordinate_role")
        }
        referenced_weather_roles = {
            str(item.get("coordinate_role", ""))
            for item in weather_section.data.get("daily", [])
            if item.get("coordinate_role")
            and str(item.get("id", "")) in referenced_ids
        }
        if referenced_weather_roles != expected_weather_roles:
            raise ValueError("Briefing output must include every saved weather coordinate role")
    if any(not item.source_ids for item in draft.news_items):
        raise ValueError("Every briefing news item must reference a source")
    if not draft.title.strip() or not draft.overview.strip():
        raise ValueError("Briefing title and overview cannot be empty")


def fallback_draft(*, target_date: str, sections: list[SectionResult]) -> BriefingDraft:
    calendar = next((item for item in sections if item.key == "calendar"), None)
    tasks = next((item for item in sections if item.key == "tasks"), None)
    agenda_items: list[BriefingAgendaItem] = []
    task_items: list[BriefingTaskItem] = []
    weather_items: list[BriefingWeatherItem] = []
    news_items: list[BriefingNewsItem] = []
    risks: list[str] = []
    if calendar and calendar.status == "completed":
        agenda_items = [
            BriefingAgendaItem(
                time=str(event.get("start_at", "")),
                title=str(event.get("title", "")),
                note=str(event.get("location", "")),
                source_ids=[str(event.get("id", ""))],
            )
            for event in calendar.data.get("events", [])
        ]
        if calendar.data.get("conflicts"):
            risks.append(f"检测到 {len(calendar.data['conflicts'])} 处日程冲突。")
    if tasks and tasks.status == "completed":
        for group, label in (("overdue", "已逾期"), ("due", "今日截止"), ("planned", "今日计划")):
            task_items.extend(
                BriefingTaskItem(
                    title=str(task.get("title", "")),
                    status=label,
                    timing=str(task.get("due_at") or task.get("planned_start_at") or ""),
                    source_ids=[str(task.get("id", ""))],
                )
                for task in tasks.data.get(group, [])
            )
        overdue_count = len(tasks.data.get("overdue", []))
        if overdue_count:
            risks.append(f"有 {overdue_count} 项任务已经逾期。")
    weather = next((item for item in sections if item.key == "weather"), None)
    if weather and weather.status == "completed":
        weather_items = [
            BriefingWeatherItem(
                date=item["date"],
                location=str(item.get("location", "")),
                summary=str(item.get("condition", "")),
                temperature_min=item.get("temperature_min"),
                temperature_max=item.get("temperature_max"),
                precipitation_probability=item.get("precipitation_probability"),
                source_ids=[str(item["id"])],
            )
            for item in weather.data.get("daily", [])
        ]
    news = next((item for item in sections if item.key == "news"), None)
    if news and news.status == "completed":
        news_items = [
            BriefingNewsItem(
                title=str(item["title"]),
                summary=str(item.get("summary", "")),
                publisher=str(item.get("publisher", "")),
                published_at=item["published_at"],
                url=str(item.get("url", "")),
                relevance="、".join(item.get("matched_topics", [])),
                source_ids=[str(item["id"])],
            )
            for item in news.data.get("items", [])
        ]
    return BriefingDraft(
        title=f"{target_date} 每日简报",
        overview=f"今日有 {len(agenda_items)} 项日程、{len(task_items)} 项相关任务。",
        agenda_items=agenda_items,
        task_items=task_items,
        weather_items=weather_items,
        news_items=news_items,
        risks=risks,
        suggestions=["优先处理临近开始的日程和已经逾期的任务。"],
    )


def render_markdown(
    draft: BriefingDraft,
    *,
    warnings: list[str],
    include_empty_sections: bool = False,
) -> str:
    lines = [f"# {draft.title}", "", draft.overview]
    if draft.agenda_items:
        lines.extend(["", "## 今日日程", ""])
        lines.extend(
            f"- **{item.time}** {item.title}" + (f" — {item.note}" if item.note else "")
            for item in draft.agenda_items
        )
    elif include_empty_sections:
        lines.extend(["", "## 今日日程", "", "暂无日程。"])
    if draft.task_items:
        lines.extend(["", "## 任务重点", ""])
        lines.extend(
            f"- **{item.status}** {item.title}" + (f"（{item.timing}）" if item.timing else "")
            for item in draft.task_items
        )
    elif include_empty_sections:
        lines.extend(["", "## 任务重点", "", "暂无相关任务。"])
    if draft.weather_items:
        lines.extend(["", "## 天气", ""])
        for weather_item in draft.weather_items:
            temperatures = ""
            if (
                weather_item.temperature_min is not None
                and weather_item.temperature_max is not None
            ):
                temperatures = (
                    f"，{weather_item.temperature_min:g}–{weather_item.temperature_max:g}°C"
                )
            rain = (
                f"，降水概率 {weather_item.precipitation_probability}%"
                if weather_item.precipitation_probability is not None
                else ""
            )
            impact = f" — {weather_item.impact}" if weather_item.impact else ""
            lines.append(
                f"- **{weather_item.date.isoformat()} · {weather_item.location}**："
                f"{weather_item.summary}{temperatures}{rain}{impact}"
            )
    elif include_empty_sections:
        lines.extend(["", "## 天气", "", "暂无天气数据。"])
    if draft.news_items:
        lines.extend(["", "## 关注新闻", ""])
        for news_item in draft.news_items:
            relevance = f" — {news_item.relevance}" if news_item.relevance else ""
            lines.append(
                f"- [{news_item.title}]({news_item.url}) · {news_item.publisher}："
                f"{news_item.summary}{relevance}"
            )
    elif include_empty_sections:
        lines.extend(["", "## 关注新闻", "", "暂无匹配新闻。"])
    if draft.risks:
        lines.extend(["", "## 风险提示", ""])
        lines.extend(f"- {item}" for item in draft.risks)
    if draft.suggestions:
        lines.extend(["", "## 今日建议", ""])
        lines.extend(f"- {item}" for item in draft.suggestions)
    if warnings:
        lines.extend(["", "## 数据警告", ""])
        lines.extend(f"- {item}" for item in warnings)
    return "\n".join(lines).strip()

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BRIEFING_SECTION_KEYS = frozenset({"calendar", "tasks", "weather", "news"})
type BriefingSectionKey = Literal["calendar", "tasks", "weather", "news"]


class SourceReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["calendar_event", "task", "weather_forecast", "news_article"]
    id: str
    title: str
    occurred_at: datetime | None = None
    url: str = ""
    publisher: str = ""


class SectionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    status: Literal["completed", "failed"]
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_code: str = ""


class BriefingAgendaItem(BaseModel):
    time: str
    title: str
    note: str = ""
    source_ids: list[str] = Field(default_factory=list)


class BriefingTaskItem(BaseModel):
    title: str
    status: str
    timing: str = ""
    source_ids: list[str] = Field(default_factory=list)


class BriefingWeatherItem(BaseModel):
    date: date
    location: str
    summary: str
    temperature_min: float | None = None
    temperature_max: float | None = None
    precipitation_probability: int | None = None
    impact: str = ""
    source_ids: list[str] = Field(default_factory=list)


class BriefingNewsItem(BaseModel):
    title: str
    summary: str
    publisher: str
    published_at: datetime
    url: str
    relevance: str = ""
    source_ids: list[str] = Field(default_factory=list)


class BriefingDraft(BaseModel):
    title: str
    overview: str
    agenda_items: list[BriefingAgendaItem] = Field(default_factory=list)
    task_items: list[BriefingTaskItem] = Field(default_factory=list)
    weather_items: list[BriefingWeatherItem] = Field(default_factory=list)
    news_items: list[BriefingNewsItem] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class BriefingRequest(BaseModel):
    definition_id: str | None = None
    target_date: date
    request_text: str = ""


class BriefingAgentRequest(BaseModel):
    """Explicit, history-independent contract delegated to the Briefing Agent."""

    model_config = ConfigDict(frozen=True)

    objective: str
    start_date: date
    end_date: date
    requested_sections: list[BriefingSectionKey]
    locations: list[str] = Field(default_factory=list)
    news_topics: list[str] = Field(default_factory=list)
    style: Literal["concise", "balanced", "detailed"] = "balanced"
    constraints: list[str] = Field(default_factory=list)
    previous_briefing_run_id: str | None = None
    previous_feedback: str | None = None

    @model_validator(mode="after")
    def validate_request(self) -> "BriefingAgentRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        if not self.objective.strip():
            raise ValueError("objective cannot be empty")
        if not self.requested_sections:
            raise ValueError("requested_sections cannot be empty")
        if len(self.requested_sections) != len(set(self.requested_sections)):
            raise ValueError("requested_sections must be unique")
        return self


class ResearchToolResult(BaseModel):
    """Machine-readable evidence returned by one Briefing Agent research tool."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    section: str
    status: Literal["completed", "partial", "no_results", "failed"]
    range_start: str = ""
    range_end: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_code: str = ""


class ResearchSummary(BaseModel):
    section: str
    status: Literal["completed", "partial", "no_results", "failed"]
    summary: str
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BriefingCoverage(BaseModel):
    start_date: date
    end_date: date
    covered_sections: list[str] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)


class BriefingAgentReport(BaseModel):
    """Final Briefing Agent deliverable plus a concise research handback."""

    draft: BriefingDraft
    research_summary: list[ResearchSummary] = Field(default_factory=list)
    failed_attempts: list[str] = Field(default_factory=list)
    unmet_requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    coverage: BriefingCoverage


class BriefingResult(BaseModel):
    run_id: str
    target_date: date
    timezone: str
    status: Literal["completed", "partial"]
    draft: BriefingDraft
    markdown: str
    sources: list[SourceReference]
    warnings: list[str]

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["calendar_event", "task"]
    id: str
    title: str
    occurred_at: datetime | None = None


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


class BriefingDraft(BaseModel):
    title: str
    overview: str
    agenda_items: list[BriefingAgendaItem] = Field(default_factory=list)
    task_items: list[BriefingTaskItem] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class BriefingRequest(BaseModel):
    definition_id: str | None = None
    target_date: date
    request_text: str = ""


class BriefingResult(BaseModel):
    run_id: str
    target_date: date
    timezone: str
    status: Literal["completed", "partial"]
    draft: BriefingDraft
    markdown: str
    sources: list[SourceReference]
    warnings: list[str]

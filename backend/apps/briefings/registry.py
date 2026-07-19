from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from django.contrib.auth.models import User

from apps.briefings.schemas import SectionResult


@dataclass(frozen=True, slots=True)
class SectionContext:
    target_date: date
    timezone: str
    current_datetime: datetime
    day_start_at: datetime
    day_end_at: datetime


class BriefingSection(Protocol):
    key: str

    def collect(self, *, user: User, context: SectionContext) -> SectionResult: ...


@dataclass(slots=True)
class BriefingRegistry:
    _sections: dict[str, BriefingSection]

    @classmethod
    def from_sections(cls, sections: Iterable[BriefingSection]) -> "BriefingRegistry":
        registered: dict[str, BriefingSection] = {}
        for section in sections:
            if section.key in registered:
                raise ValueError(f"Duplicate briefing section: {section.key}")
            registered[section.key] = section
        return cls(registered)

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(self._sections)

    def get(self, key: str) -> BriefingSection:
        try:
            return self._sections[key]
        except KeyError as exc:
            raise ValueError(f"Unknown briefing section: {key}") from exc

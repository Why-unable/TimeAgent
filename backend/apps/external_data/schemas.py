from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResolvedLocation(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    latitude: float
    longitude: float
    timezone: str
    country: str = ""
    admin1: str = ""


class DailyForecast(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    weather_code: int | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None
    precipitation_probability: int | None = None
    precipitation_sum: float | None = None
    wind_speed_max: float | None = None
    sunrise: datetime | None = None
    sunset: datetime | None = None


class WeatherForecast(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    location: ResolvedLocation
    generated_at: datetime
    daily: list[DailyForecast]
    source_url: str
    units: dict[str, str] = Field(default_factory=dict)


class NewsItemData(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    feed_name: str
    feed_url: str
    external_id: str
    title: str
    summary: str = ""
    publisher: str
    author: str = ""
    url: str
    published_at: datetime
    updated_at: datetime | None = None
    categories: list[str] = Field(default_factory=list)
    matched_topics: list[str] = Field(default_factory=list)
    score: float = 0
    fingerprint: str
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class NewsSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[NewsItemData]
    warnings: list[str] = Field(default_factory=list)
    selected_feeds: list[str] = Field(default_factory=list)
    successful_feeds: list[str] = Field(default_factory=list)
    uncovered_topics: list[str] = Field(default_factory=list)

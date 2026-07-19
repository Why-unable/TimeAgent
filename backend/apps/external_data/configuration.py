from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from django.conf import settings
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class FeedDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    url: HttpUrl
    publisher: str
    topics: list[str] = Field(min_length=1)
    priority: int = Field(default=50, ge=0, le=100)

    @field_validator("name", "publisher")
    @classmethod
    def non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be empty")
        return normalized

    @field_validator("topics")
    @classmethod
    def normalized_topics(cls, value: list[str]) -> list[str]:
        topics = [item.strip() for item in value if item.strip()]
        if not topics:
            raise ValueError("feed topics cannot be empty")
        return topics

    @field_validator("url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("feed URL must use HTTPS")
        return value


class WeatherProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = "open_meteo"
    forecast_url: HttpUrl
    geocoding_url: HttpUrl
    timeout_seconds: float = Field(default=8, gt=0, le=30)
    forecast_days: int = Field(default=3, ge=1, le=7)

    @field_validator("forecast_url", "geocoding_url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("weather provider URL must use HTTPS")
        return value


class NewsProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = "rss"
    timeout_seconds: float = Field(default=8, gt=0, le=30)
    lookback_hours: int = Field(default=24, ge=1, le=168)
    max_items: int = Field(default=12, ge=1, le=50)
    max_items_per_feed: int = Field(default=30, ge=1, le=100)
    max_concurrent_feeds: int = Field(default=4, ge=1, le=10)
    topic_aliases: dict[str, list[str]] = Field(default_factory=dict)
    feeds: list[FeedDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_feeds(self) -> NewsProviderConfig:
        names = [feed.name.casefold() for feed in self.feeds]
        urls = [str(feed.url) for feed in self.feeds]
        if len(names) != len(set(names)):
            raise ValueError("feed names must be unique")
        if len(urls) != len(set(urls)):
            raise ValueError("feed URLs must be unique")
        return self


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    config_version: int = 1
    weather: WeatherProviderConfig
    news: NewsProviderConfig


def _default_path() -> Path:
    configured = os.getenv("TIME_AGENT_PROVIDER_CONFIG_PATH", "").strip()
    return Path(configured) if configured else Path(settings.BASE_DIR) / "config" / "providers.yaml"


@lru_cache(maxsize=1)
def get_provider_config(path: str | Path | None = None) -> ProviderConfig:
    config_path = Path(path) if path is not None else _default_path()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Provider configuration root must be an object")
    return ProviderConfig.model_validate(raw)

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from apps.external_data.configuration import get_provider_config
from apps.external_data.models import ExternalNewsItem
from apps.external_data.providers import (
    NewsProvider,
    OpenMeteoWeatherProvider,
    RssNewsProvider,
    WeatherProvider,
)
from apps.external_data.providers.news import canonicalize_url
from apps.external_data.schemas import NewsItemData, WeatherForecast
from apps.preferences.services import UserPreferenceService


@dataclass(frozen=True, slots=True)
class NewsCollection:
    items: list[ExternalNewsItem]
    matched_topics: dict[str, list[str]]
    warnings: list[str]
    selected_feeds: list[str]
    successful_feeds: list[str]


class WeatherLocationNotConfiguredError(ValueError):
    pass


class WeatherDataService:
    @staticmethod
    def forecast_for_user(
        *,
        user: User,
        start_date: date,
        end_date: date | None = None,
        requested_at: datetime,
        locale: str,
        location_query: str | None = None,
        provider: WeatherProvider | None = None,
    ) -> WeatherForecast:
        preference = UserPreferenceService.get_for_user(user)
        effective_location = (
            location_query.strip()
            if location_query is not None
            else (preference.weather_location.strip() if preference else "")
        )
        if not effective_location:
            raise WeatherLocationNotConfiguredError("请先在时间偏好中配置天气地点。")
        effective_end = end_date or start_date
        if effective_end < start_date:
            raise ValueError("Weather end_date must not be earlier than start_date")
        requested_days = (effective_end - start_date).days + 1
        maximum_days = get_provider_config().weather.forecast_days
        if requested_days > maximum_days:
            raise ValueError(f"Weather provider supports at most {maximum_days} forecast days")
        resolved_provider = provider or OpenMeteoWeatherProvider()
        location = resolved_provider.resolve_location(effective_location, language=locale)
        return resolved_provider.forecast(
            location,
            start_date=start_date,
            days=requested_days,
            requested_at=requested_at,
        )


class NewsDataService:
    @staticmethod
    def collect_for_user(
        *,
        user: User,
        start_at: datetime,
        end_at: datetime,
        topics: list[str] | None = None,
        limit: int | None = None,
        provider: NewsProvider | None = None,
    ) -> NewsCollection:
        preference = UserPreferenceService.get_for_user(user)
        effective_topics = (
            [item.strip() for item in topics if item.strip()]
            if topics is not None
            else (list(preference.news_topics) if preference else [])
        )
        configured_limit = get_provider_config().news.max_items
        result = (provider or RssNewsProvider()).search(
            effective_topics,
            start_at=start_at,
            end_at=end_at,
            limit=min(limit or configured_limit, configured_limit),
        )
        deduplicated = _deduplicate(result.items)
        records: list[ExternalNewsItem] = []
        matched_topics: dict[str, list[str]] = {}
        for item in deduplicated:
            record = NewsDataService._upsert(item)
            records.append(record)
            matched_topics[str(record.pk)] = item.matched_topics
        return NewsCollection(
            items=records,
            matched_topics=matched_topics,
            warnings=result.warnings,
            selected_feeds=result.selected_feeds,
            successful_feeds=result.successful_feeds,
        )

    @staticmethod
    def _upsert(item: NewsItemData) -> ExternalNewsItem:
        defaults = {
            "canonical_url": canonicalize_url(str(item.url)),
            "title": item.title,
            "summary": item.summary,
            "publisher": item.publisher,
            "author": item.author,
            "published_at": item.published_at,
            "source_updated_at": item.updated_at,
            "categories": item.categories,
            "content_fingerprint": item.fingerprint,
        }
        try:
            # Keep a uniqueness violation inside its own savepoint so the
            # fallback lookup runs in a healthy transaction.
            with transaction.atomic():
                record, _ = ExternalNewsItem.objects.update_or_create(
                    provider=item.provider,
                    feed_url=str(item.feed_url),
                    external_id=item.external_id,
                    defaults={"feed_name": item.feed_name, **defaults},
                )
        except IntegrityError:
            record = ExternalNewsItem.objects.get(content_fingerprint=item.fingerprint)
        return record


def _deduplicate(items: list[NewsItemData]) -> list[NewsItemData]:
    selected: list[NewsItemData] = []
    urls: set[str] = set()
    fingerprints: set[str] = set()
    for item in items:
        url = canonicalize_url(str(item.url))
        if url in urls or item.fingerprint in fingerprints:
            continue
        if any(
            existing.published_at.date() == item.published_at.date()
            and SequenceMatcher(None, existing.title.casefold(), item.title.casefold()).ratio()
            >= 0.9
            for existing in selected
        ):
            continue
        selected.append(item)
        urls.add(url)
        fingerprints.add(item.fingerprint)
    return selected

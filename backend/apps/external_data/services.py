from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Literal

import httpx
from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from apps.external_data.administrative_areas import administrative_area_code
from apps.external_data.configuration import get_provider_config
from apps.external_data.models import ExternalNewsItem
from apps.external_data.providers import (
    AmapWeatherProvider,
    NewsProvider,
    OpenMeteoWeatherProvider,
    RssNewsProvider,
    WeatherProvider,
)
from apps.external_data.providers.news import canonicalize_url
from apps.external_data.schemas import NewsItemData, ResolvedLocation, WeatherForecast
from apps.preferences.services import UserPreferenceService
from apps.preferences.weather_location import normalized_weather_location_data

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NewsCollection:
    items: list[ExternalNewsItem]
    matched_topics: dict[str, list[str]]
    warnings: list[str]
    selected_feeds: list[str]
    successful_feeds: list[str]


class WeatherLocationNotConfiguredError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WeatherForecastVariant:
    coordinate_role: Literal["administrative_center", "device_gps", "requested_location"]
    display_label: str
    forecast: WeatherForecast


@dataclass(frozen=True, slots=True)
class WeatherForecastCollection:
    forecasts: list[WeatherForecastVariant]
    warnings: list[str]


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
        requested_location = location_query.strip() if location_query is not None else ""
        use_selected_location = location_query is None or _matches_selected_location(
            preference,
            requested_location,
        )
        selected_location = _selected_location(preference) if use_selected_location else None
        effective_location = requested_location or (
            preference.weather_location.strip() if preference else ""
        )
        if not effective_location and selected_location is None:
            raise WeatherLocationNotConfiguredError("请先在时间偏好中配置天气地点。")
        effective_end = end_date or start_date
        if effective_end < start_date:
            raise ValueError("Weather end_date must not be earlier than start_date")
        requested_days = (effective_end - start_date).days + 1
        maximum_days = get_provider_config().weather.forecast_days
        if requested_days > maximum_days:
            raise ValueError(f"Weather provider supports at most {maximum_days} forecast days")
        providers = [provider] if provider is not None else _weather_providers()
        last_error: Exception | None = None
        for resolved_provider in providers:
            try:
                location = selected_location or resolved_provider.resolve_location(
                    effective_location,
                    language=locale,
                )
                return resolved_provider.forecast(
                    location,
                    start_date=start_date,
                    days=requested_days,
                    requested_at=requested_at,
                )
            except (httpx.HTTPError, LookupError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "weather_provider_failed",
                    extra={
                        "provider": getattr(
                            resolved_provider,
                            "name",
                            type(resolved_provider).__name__,
                        ),
                        "error_type": type(exc).__name__,
                    },
                )
        assert last_error is not None
        raise last_error

    @staticmethod
    def forecast_variants_for_user(
        *,
        user: User,
        start_date: date,
        end_date: date | None = None,
        requested_at: datetime,
        locale: str,
        location_query: str | None = None,
        coordinate_provider: WeatherProvider | None = None,
    ) -> WeatherForecastCollection:
        preference = UserPreferenceService.get_for_user(user)
        requested_location = location_query.strip() if location_query is not None else ""
        use_selected_location = location_query is None or _matches_selected_location(
            preference,
            requested_location,
        )
        if not use_selected_location:
            forecast = WeatherDataService.forecast_for_user(
                user=user,
                start_date=start_date,
                end_date=end_date,
                requested_at=requested_at,
                locale=locale,
                location_query=requested_location,
            )
            return WeatherForecastCollection(
                forecasts=[
                    WeatherForecastVariant(
                        coordinate_role="requested_location",
                        display_label=requested_location,
                        forecast=forecast,
                    )
                ],
                warnings=[],
            )

        locations = _selected_location_variants(preference)
        if not locations:
            raise WeatherLocationNotConfiguredError("请先在时间偏好中配置天气地点。")
        effective_end = end_date or start_date
        if effective_end < start_date:
            raise ValueError("Weather end_date must not be earlier than start_date")
        requested_days = (effective_end - start_date).days + 1
        maximum_days = get_provider_config().weather.forecast_days
        if requested_days > maximum_days:
            raise ValueError(f"Weather provider supports at most {maximum_days} forecast days")

        provider = coordinate_provider or OpenMeteoWeatherProvider()
        forecasts: list[WeatherForecastVariant] = []
        warnings: list[str] = []
        last_error: Exception | None = None
        roles = {item.coordinate_role for item in locations}
        if "administrative_center" not in roles:
            warnings.append("尚未保存手动行政区代表点，本次不含行政区中心坐标天气。")
        if "device_gps" not in roles:
            warnings.append("尚未保存手机当前位置 GPS，本次不含设备精确坐标天气。")
        for location in locations:
            try:
                forecast = provider.forecast(
                    location.location,
                    start_date=start_date,
                    days=requested_days,
                    requested_at=requested_at,
                )
            except (httpx.HTTPError, LookupError, ValueError) as exc:
                last_error = exc
                warnings.append(f"{location.display_label}天气查询失败（{type(exc).__name__}）。")
                logger.warning(
                    "coordinate_weather_provider_failed",
                    extra={
                        "provider": getattr(provider, "name", type(provider).__name__),
                        "coordinate_role": location.coordinate_role,
                        "error_type": type(exc).__name__,
                    },
                )
                continue
            forecasts.append(
                WeatherForecastVariant(
                    coordinate_role=location.coordinate_role,
                    display_label=location.display_label,
                    forecast=forecast,
                )
            )
        if not forecasts:
            if last_error is not None:
                raise last_error
            raise WeatherLocationNotConfiguredError("没有可用于天气查询的坐标。")
        return WeatherForecastCollection(forecasts=forecasts, warnings=warnings)


@dataclass(frozen=True, slots=True)
class _SelectedLocationVariant:
    coordinate_role: Literal["administrative_center", "device_gps"]
    display_label: str
    location: ResolvedLocation


def _selected_location(preference: object | None) -> ResolvedLocation | None:
    variants = _selected_location_variants(preference)
    return variants[0].location if variants else None


def _selected_location_variants(
    preference: object | None,
) -> list[_SelectedLocationVariant]:
    data = normalized_weather_location_data(
        getattr(preference, "weather_location_data", None)
    )
    if not data:
        return []
    label = str(data.get("label", "")).strip()
    timezone = str(data.get("timezone", "")).strip()
    country = str(data.get("country", ""))
    admin1 = str(data.get("admin1", ""))
    name = str(data.get("name", ""))
    variants: list[_SelectedLocationVariant] = []
    administrative = data.get("administrative_coordinates")
    if isinstance(administrative, dict):
        adcode = str(data.get("adcode", ""))
        if len(adcode) != 6 or not adcode.isdigit():
            adcode = administrative_area_code(
                province=str(data.get("province", "")),
                city=str(data.get("city", "")),
                district=str(data.get("district", "")),
            )
        location = _resolved_stored_coordinates(
            administrative,
            name=name,
            timezone=timezone,
            country=country,
            admin1=admin1,
            provider_location_id=adcode
            or str(administrative.get("provider_location_id", "")),
        )
        if location is not None:
            variants.append(
                _SelectedLocationVariant(
                    coordinate_role="administrative_center",
                    display_label=f"手动行政区代表点（{label}）",
                    location=location,
                )
            )
    current = data.get("current_coordinates")
    if isinstance(current, dict):
        current_label = str(current.get("label", "")).strip()
        location = _resolved_stored_coordinates(
            current,
            name=current_label or "手机当前位置",
            timezone=timezone,
            country=country,
            admin1=admin1,
            provider_location_id=str(current.get("provider_location_id", "")),
        )
        if location is not None:
            variants.append(
                _SelectedLocationVariant(
                    coordinate_role="device_gps",
                    display_label=(
                        f"手机当前位置 GPS（{current_label}）"
                        if current_label and current_label != label
                        else "手机当前位置 GPS（设备精确坐标）"
                    ),
                    location=location,
                )
            )
    return variants


def _resolved_stored_coordinates(
    coordinates: Mapping[str, object],
    *,
    name: str,
    timezone: str,
    country: str,
    admin1: str,
    provider_location_id: str,
) -> ResolvedLocation | None:
    latitude = coordinates.get("latitude")
    longitude = coordinates.get("longitude")
    if (
        not isinstance(latitude, (int, float))
        or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float))
        or isinstance(longitude, bool)
    ):
        return None
    try:
        return ResolvedLocation(
            name=name,
            latitude=float(latitude),
            longitude=float(longitude),
            timezone=timezone,
            country=country,
            admin1=admin1,
            provider_location_id=provider_location_id,
        )
    except (KeyError, TypeError, ValueError):
        return None


_LOCATION_LABEL_SEPARATOR = re.compile(r"[\s/,，;；]+")


def _matches_selected_location(preference: object | None, requested_location: str) -> bool:
    if preference is None or not requested_location:
        return False
    data = getattr(preference, "weather_location_data", None)
    candidates = [getattr(preference, "weather_location", "")]
    if isinstance(data, dict):
        candidates.extend([data.get("label", ""), data.get("name", "")])
    requested = _LOCATION_LABEL_SEPARATOR.sub("", requested_location).casefold()
    return any(
        requested == _LOCATION_LABEL_SEPARATOR.sub("", str(candidate)).casefold()
        for candidate in candidates
        if str(candidate).strip()
    )


def _weather_providers() -> list[WeatherProvider]:
    providers: list[WeatherProvider] = []
    if settings.AMAP_WEATHER_ENABLED and settings.AMAP_WEB_SERVICE_KEY:
        providers.append(
            AmapWeatherProvider(
                api_key=settings.AMAP_WEB_SERVICE_KEY,
                timeout_seconds=settings.AMAP_WEATHER_TIMEOUT_SECONDS,
            )
        )
    providers.append(OpenMeteoWeatherProvider())
    return providers


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

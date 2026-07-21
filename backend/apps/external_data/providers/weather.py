from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from apps.external_data.configuration import WeatherProviderConfig, get_provider_config
from apps.external_data.schemas import DailyForecast, ResolvedLocation, WeatherForecast


class WeatherProvider(Protocol):
    def resolve_location(self, query: str, *, language: str) -> ResolvedLocation: ...

    def forecast(
        self,
        location: ResolvedLocation,
        *,
        start_date: date,
        days: int,
        requested_at: datetime,
    ) -> WeatherForecast: ...


class OpenMeteoWeatherProvider:
    name = "open_meteo"

    def __init__(
        self,
        config: WeatherProviderConfig | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config or get_provider_config().weather
        self._client = client

    def _request(
        self,
        url: str,
        *,
        params: dict[str, str | int | float | bool | None],
    ) -> httpx.Response:
        if self._client is not None:
            response = self._client.get(url, params=params)
        else:
            with httpx.Client(
                timeout=self.config.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "TimeAgent/0.1 weather-provider"},
            ) as client:
                response = client.get(url, params=params)
        response.raise_for_status()
        return response

    def resolve_location(self, query: str, *, language: str) -> ResolvedLocation:
        normalized = query.strip()
        if len(normalized) < 2:
            raise ValueError("Weather location must contain at least two characters")
        names, qualifiers = _location_search_terms(normalized)
        candidates: dict[str, dict[str, Any]] = {}
        for name in names:
            response = self._request(
                str(self.config.geocoding_url),
                params={"name": name, "count": 20, "language": language.split("-")[0]},
            )
            payload = response.json()
            results = payload.get("results", []) if isinstance(payload, dict) else []
            for item in results:
                if not isinstance(item, dict):
                    continue
                identity = str(
                    item.get("id")
                    or f"{item.get('latitude')}:{item.get('longitude')}"
                )
                candidates[identity] = item
        ranked = sorted(
            (
                (_location_score(item, names[0], qualifiers), item)
                for item in candidates.values()
                if _matches_qualifiers(item, qualifiers)
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not ranked:
            raise LookupError(f"Weather location was not found: {normalized}")
        item = ranked[0][1]
        return ResolvedLocation(
            name=str(item["name"]),
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
            timezone=str(item["timezone"]),
            country=str(item.get("country", "")),
            admin1=str(item.get("admin1", "")),
        )
    def forecast(
        self,
        location: ResolvedLocation,
        *,
        start_date: date,
        days: int,
        requested_at: datetime,
    ) -> WeatherForecast:
        bounded_days = max(1, min(days, self.config.forecast_days))
        params: dict[str, str | int | float | bool | None] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": location.timezone,
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=bounded_days - 1)).isoformat(),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "precipitation_sum",
                    "wind_speed_10m_max",
                    "sunrise",
                    "sunset",
                ]
            ),
        }
        response = self._request(str(self.config.forecast_url), params=params)
        payload = response.json()
        daily = payload.get("daily", {}) if isinstance(payload, dict) else {}
        dates = daily.get("time", [])
        forecasts = [
            DailyForecast(
                date=date.fromisoformat(str(day)),
                weather_code=_int_at(daily, "weather_code", index),
                temperature_max=_float_at(daily, "temperature_2m_max", index),
                temperature_min=_float_at(daily, "temperature_2m_min", index),
                precipitation_probability=_int_at(daily, "precipitation_probability_max", index),
                precipitation_sum=_float_at(daily, "precipitation_sum", index),
                wind_speed_max=_float_at(daily, "wind_speed_10m_max", index),
                sunrise=_datetime_at(daily, "sunrise", index, location.timezone),
                sunset=_datetime_at(daily, "sunset", index, location.timezone),
            )
            for index, day in enumerate(dates)
        ]
        if not forecasts:
            raise ValueError("Weather provider returned no daily forecast")
        source_url = f"{self.config.forecast_url}?{urlencode(params)}"
        units = payload.get("daily_units", {}) if isinstance(payload, dict) else {}
        return WeatherForecast(
            provider=self.name,
            location=location,
            generated_at=requested_at,
            daily=forecasts,
            source_url=source_url,
            units={str(key): str(value) for key, value in units.items()},
        )


_LOCATION_SEPARATOR = re.compile(r"[,，;；/]+")
_ADMIN_SUFFIXES = ("特别行政区", "自治区", "自治州", "地区", "省", "市", "县", "区")


def _location_search_terms(query: str) -> tuple[list[str], list[str]]:
    parts = [part.strip() for part in _LOCATION_SEPARATOR.split(query) if part.strip()]
    primary = parts[0] if parts else query
    names = [query]
    if primary not in names:
        names.append(primary)
    if _contains_cjk(primary) and not primary.endswith(_ADMIN_SUFFIXES):
        names.append(f"{primary}市")
    return list(dict.fromkeys(names)), parts[1:]


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def _normalized_place(value: object) -> str:
    normalized = re.sub(r"[\s\-_'’]", "", str(value).casefold())
    for suffix in _ADMIN_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _candidate_fields(item: dict[str, Any]) -> list[str]:
    return [
        _normalized_place(item.get(key, ""))
        for key in (
            "name",
            "admin1",
            "admin2",
            "admin3",
            "admin4",
            "country",
            "country_code",
        )
        if item.get(key)
    ]


def _matches_qualifiers(item: dict[str, Any], qualifiers: list[str]) -> bool:
    fields = _candidate_fields(item)
    return all(
        any(
            _normalized_place(qualifier) == field
            or _normalized_place(qualifier) in field
            or field in _normalized_place(qualifier)
            for field in fields
        )
        for qualifier in qualifiers
    )


def _location_score(item: dict[str, Any], primary: str, qualifiers: list[str]) -> float:
    requested = _normalized_place(primary)
    candidate = _normalized_place(item.get("name", ""))
    score = 0.0
    if candidate == requested:
        score += 100
    elif requested in candidate or candidate in requested:
        score += 50
    score += 100 * len(qualifiers)
    feature_code = str(item.get("feature_code", ""))
    if feature_code == "PPLC":
        score += 30
    elif feature_code.startswith("PPLA"):
        score += 20
    population = item.get("population")
    if isinstance(population, (int, float)) and population > 0:
        score += min(30, math.log10(population) * 4)
    return score


def _value_at(data: dict[str, object], key: str, index: int) -> Any:
    values = data.get(key)
    if not isinstance(values, list) or index >= len(values) or values[index] is None:
        return None
    return values[index]


def _int_at(data: dict[str, object], key: str, index: int) -> int | None:
    value = _value_at(data, key, index)
    return int(value) if value is not None else None


def _float_at(data: dict[str, object], key: str, index: int) -> float | None:
    value = _value_at(data, key, index)
    return float(value) if value is not None else None


def _datetime_at(
    data: dict[str, object], key: str, index: int, timezone_name: str
) -> datetime | None:
    values = data.get(key)
    if not isinstance(values, list) or index >= len(values) or values[index] is None:
        return None
    from common.time import get_timezone

    return datetime.fromisoformat(str(values[index])).replace(tzinfo=get_timezone(timezone_name))

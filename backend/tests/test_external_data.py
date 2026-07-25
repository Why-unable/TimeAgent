from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from pydantic import ValidationError
from rest_framework.test import APIClient

from apps.briefings.rendering import render_markdown, validate_draft
from apps.briefings.schemas import (
    BriefingDraft,
    BriefingNewsItem,
    BriefingWeatherItem,
    SectionResult,
    SourceReference,
)
from apps.external_data.configuration import (
    NewsProviderConfig,
    WeatherProviderConfig,
    get_provider_config,
)
from apps.external_data.models import ExternalNewsItem
from apps.external_data.providers.news import RssNewsProvider, canonicalize_url
from apps.external_data.providers.weather import OpenMeteoWeatherProvider
from apps.external_data.schemas import (
    DailyForecast,
    NewsItemData,
    NewsSearchResult,
    ResolvedLocation,
    WeatherForecast,
)
from apps.external_data.services import NewsDataService, WeatherDataService
from apps.preferences.services import UserPreferenceService


def _news_config(*feeds: dict[str, Any]) -> NewsProviderConfig:
    return NewsProviderConfig.model_validate(
        {
            "provider": "rss",
            "timeout_seconds": 2,
            "lookback_hours": 24,
            "max_items": 10,
            "max_items_per_feed": 10,
            "topic_aliases": {
                "artificial intelligence": ["ai", "人工智能", "llm"],
                "python": ["python"],
            },
            "feeds": list(feeds),
        }
    )


def _feed(name: str, url: str, topics: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "url": url,
        "publisher": name,
        "topics": topics,
        "priority": 80,
    }


def _rss(title: str, *, link: str, published: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Test</title>
    <item><guid>{link}</guid><title>{title}</title><link>{link}</link>
    <description>New AI and Python release details.</description>
    <pubDate>{published}</pubDate></item></channel></rss>""".encode()


def test_provider_catalog_contains_only_https_trusted_feeds() -> None:
    config = get_provider_config()

    assert config.weather.provider == "open_meteo"
    assert {feed.name for feed in config.news.feeds} >= {
        "OpenAI News",
        "GitHub Blog",
        "Python Insider",
        "China News Service Latest",
        "China News Service Finance",
        "InfoQ China",
        "QbitAI",
        "OSChina",
        "Solidot",
        "Ifanr",
        "36Kr",
    }
    assert all(str(feed.url).startswith("https://") for feed in config.news.feeds)


def test_domestic_topic_alias_routes_only_declared_trusted_feeds() -> None:
    cache.clear()
    config = get_provider_config()
    provider = RssNewsProvider(
        config.news,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=b'<?xml version="1.0"?><rss version="2.0"><channel/></rss>',
                )
            )
        ),
    )

    result = provider.search(
        ["国内财经"],
        start_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
        end_at=datetime(2026, 7, 19, 8, tzinfo=UTC),
        limit=10,
    )

    assert result.selected_feeds == ["China News Service Finance", "36Kr"]
    assert result.uncovered_topics == []


def test_provider_configuration_rejects_non_https_feed() -> None:
    with pytest.raises(ValidationError):
        _news_config(_feed("Unsafe", "http://example.test/feed.xml", ["python"]))


def test_weather_and_news_markdown_requires_and_preserves_sources() -> None:
    sections = [
        SectionResult(
            key="weather",
            status="completed",
            sources=[
                SourceReference(
                    kind="weather_forecast",
                    id="weather:2026-07-19",
                    title="Shanghai weather",
                    url="https://weather.test/forecast",
                )
            ],
        ),
        SectionResult(
            key="news",
            status="completed",
            sources=[
                SourceReference(
                    kind="news_article",
                    id="news:1",
                    title="Python release",
                    url="https://news.test/python",
                    publisher="Python Software Foundation",
                )
            ],
        ),
    ]
    draft = BriefingDraft(
        title="Daily briefing",
        overview="Weather and news are available.",
        weather_items=[
            BriefingWeatherItem(
                date=date(2026, 7, 19),
                location="Shanghai",
                summary="Rain",
                source_ids=["weather:2026-07-19"],
            )
        ],
        news_items=[
            BriefingNewsItem(
                title="Python release",
                summary="A new release is available.",
                publisher="Python Software Foundation",
                published_at=datetime(2026, 7, 19, 2, tzinfo=UTC),
                url="https://news.test/python",
                source_ids=["news:1"],
            )
        ],
    )

    validate_draft(draft, sections)
    markdown = render_markdown(draft, warnings=[])

    assert "Shanghai" in markdown
    assert "[Python release](https://news.test/python)" in markdown


def test_open_meteo_resolves_location_and_normalizes_forecast() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "geocoding" in request.url.host:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Shanghai",
                            "latitude": 31.23,
                            "longitude": 121.47,
                            "timezone": "Asia/Shanghai",
                            "country": "China",
                            "admin1": "Shanghai",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "daily": {
                    "time": ["2026-07-19"],
                    "weather_code": [61],
                    "temperature_2m_max": [31.5],
                    "temperature_2m_min": [25.0],
                    "precipitation_probability_max": [80],
                    "precipitation_sum": [8.2],
                    "wind_speed_10m_max": [20.0],
                    "sunrise": ["2026-07-19T05:03"],
                    "sunset": ["2026-07-19T18:57"],
                },
                "daily_units": {"temperature_2m_max": "°C"},
            },
        )

    config = WeatherProviderConfig.model_validate(
        {
            "forecast_url": "https://api.open-meteo.test/v1/forecast",
            "geocoding_url": "https://geocoding.open-meteo.test/v1/search",
            "forecast_days": 3,
        }
    )
    provider = OpenMeteoWeatherProvider(
        config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    location = provider.resolve_location("上海", language="zh-CN")
    forecast = provider.forecast(
        location,
        start_date=date(2026, 7, 19),
        days=1,
        requested_at=datetime(2026, 7, 19, 0, 0, tzinfo=UTC),
    )

    assert location.timezone == "Asia/Shanghai"
    assert forecast.daily[0].temperature_max == 31.5
    assert forecast.daily[0].precipitation_probability == 80


def test_open_meteo_disambiguates_chinese_city_with_administrative_qualifier() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["name"]
        if query == "珠海":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1,
                            "name": "珠海",
                            "latitude": 35.87124,
                            "longitude": 119.99638,
                            "timezone": "Asia/Shanghai",
                            "country": "中国",
                            "admin1": "山东",
                            "admin2": "青岛市",
                            "feature_code": "PPL",
                        }
                    ]
                },
            )
        if query == "珠海市":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 2,
                            "name": "珠海市",
                            "latitude": 22.27694,
                            "longitude": 113.56778,
                            "timezone": "Asia/Shanghai",
                            "country": "中国",
                            "admin1": "广东",
                            "admin2": "珠海市",
                            "feature_code": "PPLA2",
                            "population": 2_207_090,
                        }
                    ]
                },
            )
        return httpx.Response(200, json={})

    config = WeatherProviderConfig.model_validate(
        {
            "forecast_url": "https://api.open-meteo.test/v1/forecast",
            "geocoding_url": "https://geocoding.open-meteo.test/v1/search",
            "forecast_days": 7,
        }
    )
    provider = OpenMeteoWeatherProvider(
        config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    qualified = provider.resolve_location("珠海, 广东", language="zh-CN")
    unqualified = provider.resolve_location("珠海", language="zh-CN")

    assert qualified.name == "珠海市"
    assert qualified.admin1 == "广东"
    assert qualified.latitude == 22.27694
    assert unqualified.name == "珠海市"


def test_open_meteo_rejects_candidates_outside_explicit_administrative_area() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 1,
                        "name": "珠海",
                        "latitude": 35.87124,
                        "longitude": 119.99638,
                        "timezone": "Asia/Shanghai",
                        "country": "中国",
                        "admin1": "山东",
                        "admin2": "青岛市",
                    }
                ]
            },
        )

    config = WeatherProviderConfig.model_validate(
        {
            "forecast_url": "https://api.open-meteo.test/v1/forecast",
            "geocoding_url": "https://geocoding.open-meteo.test/v1/search",
            "forecast_days": 7,
        }
    )
    provider = OpenMeteoWeatherProvider(
        config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LookupError, match="珠海, 广东"):
        provider.resolve_location("珠海, 广东", language="zh-CN")


def test_rss_provider_routes_topics_filters_time_and_preserves_sources() -> None:
    cache.clear()
    config = _news_config(
        _feed("AI Feed", "https://example.test/ai.xml", ["artificial intelligence"]),
        _feed("Python Feed", "https://example.test/python.xml", ["python"]),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ai.xml"
        return httpx.Response(
            200,
            content=_rss(
                "New LLM agent framework",
                link="https://example.test/story?utm_source=rss",
                published="Sun, 19 Jul 2026 02:00:00 GMT",
            ),
            headers={"ETag": "test-v1"},
        )

    provider = RssNewsProvider(
        config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.search(
        ["人工智能"],
        start_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
        end_at=datetime(2026, 7, 19, 8, tzinfo=UTC),
        limit=10,
    )

    assert result.selected_feeds == ["AI Feed"]
    assert result.successful_feeds == ["AI Feed"]
    assert len(result.items) == 1
    assert result.items[0].url == "https://example.test/story"
    assert "artificial intelligence" in result.items[0].matched_topics
    assert result.uncovered_topics == []


def test_rss_provider_searches_trusted_catalog_for_unconfigured_topic() -> None:
    cache.clear()
    config = _news_config(
        _feed("General One", "https://general-one.test/feed.xml", ["technology"]),
        _feed("General Two", "https://general-two.test/feed.xml", ["finance"]),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        title = "量子计算取得新进展" if request.url.host == "general-two.test" else "普通科技资讯"
        return httpx.Response(
            200,
            content=_rss(
                title,
                link=f"https://{request.url.host}/story",
                published="Sun, 19 Jul 2026 02:00:00 GMT",
            ),
        )

    provider = RssNewsProvider(
        config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.search(
        ["量子计算"],
        start_at=datetime(2026, 7, 18, tzinfo=UTC),
        end_at=datetime(2026, 7, 20, tzinfo=UTC),
        limit=10,
    )

    assert result.selected_feeds == ["General One", "General Two"]
    assert [item.title for item in result.items] == ["量子计算取得新进展"]
    assert result.uncovered_topics == ["量子计算"]


def test_rss_provider_keeps_success_when_another_feed_times_out() -> None:
    cache.clear()
    config = _news_config(
        _feed("Broken AI", "https://broken.test/feed.xml", ["artificial intelligence"]),
        _feed("Working AI", "https://working.test/feed.xml", ["artificial intelligence"]),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "broken.test":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(
            200,
            content=_rss(
                "AI provider update",
                link="https://working.test/story",
                published="Sun, 19 Jul 2026 02:00:00 GMT",
            ),
        )

    result = RssNewsProvider(
        config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).search(
        ["AI"],
        start_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
        end_at=datetime(2026, 7, 19, 8, tzinfo=UTC),
        limit=10,
    )

    assert len(result.items) == 1
    assert result.successful_feeds == ["Working AI"]
    assert "Broken AI 暂时不可用" in result.warnings[0]


def test_rss_provider_bypasses_unavailable_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.external_data.providers import news as news_module

    config = _news_config(_feed("Python Feed", "https://example.test/feed.xml", ["python"]))
    monkeypatch.setattr(news_module, "_cache_unavailable_until", 0.0)
    monkeypatch.setattr(news_module.cache, "get", lambda key: (_ for _ in ()).throw(OSError()))
    provider = RssNewsProvider(
        config,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=_rss(
                        "Python release",
                        link="https://example.test/python",
                        published="Sun, 19 Jul 2026 02:00:00 GMT",
                    ),
                )
            )
        ),
    )

    result = provider.search(
        ["Python"],
        start_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
        end_at=datetime(2026, 7, 19, 8, tzinfo=UTC),
        limit=10,
    )

    assert len(result.items) == 1


class FakeNewsProvider:
    def search(
        self,
        topics: list[str],
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int,
    ) -> NewsSearchResult:
        del topics, start_at, end_at, limit
        common = {
            "provider": "rss",
            "feed_name": "AI Feed",
            "feed_url": "https://example.test/feed.xml",
            "publisher": "Example",
            "published_at": datetime(2026, 7, 19, 2, tzinfo=UTC),
            "matched_topics": ["artificial intelligence"],
        }
        return NewsSearchResult(
            items=[
                NewsItemData.model_validate(
                    {
                        **common,
                        "external_id": "one",
                        "title": "A major AI model release",
                        "summary": "First report.",
                        "url": "https://example.test/story?utm_source=feed",
                        "fingerprint": "a" * 64,
                    }
                ),
                NewsItemData.model_validate(
                    {
                        **common,
                        "external_id": "two",
                        "title": "A major AI model release",
                        "summary": "Duplicate report.",
                        "url": "https://example.test/story",
                        "fingerprint": "a" * 64,
                    }
                ),
            ],
            selected_feeds=["AI Feed"],
            successful_feeds=["AI Feed"],
        )


@pytest.mark.django_db
def test_news_service_deduplicates_and_persists_provider_items() -> None:
    user = User.objects.create_user(username="news-provider-user")
    UserPreferenceService.update_for_user(user, {"news_topics": ["人工智能"]})

    result = NewsDataService.collect_for_user(
        user=user,
        start_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
        end_at=datetime(2026, 7, 19, 8, tzinfo=UTC),
        provider=FakeNewsProvider(),
    )

    assert len(result.items) == 1
    assert ExternalNewsItem.objects.count() == 1
    assert result.items[0].canonical_url == "https://example.test/story"
    assert canonicalize_url("https://x.test/a?utm_source=rss#top") == "https://x.test/a"


class RecordingWeatherProvider:
    def __init__(self) -> None:
        self.days = 0

    def resolve_location(self, query: str, *, language: str) -> ResolvedLocation:
        del query, language
        return ResolvedLocation(
            name="Shanghai",
            latitude=31.23,
            longitude=121.47,
            timezone="Asia/Shanghai",
            country="China",
        )

    def forecast(
        self,
        location: ResolvedLocation,
        *,
        start_date: date,
        days: int,
        requested_at: datetime,
    ) -> WeatherForecast:
        self.days = days
        return WeatherForecast(
            provider="recording_weather",
            location=location,
            generated_at=requested_at,
            daily=[DailyForecast(date=start_date + timedelta(days=index)) for index in range(days)],
            source_url="https://weather.test/forecast",
        )


@pytest.mark.django_db
def test_weather_service_honors_requested_range_up_to_provider_limit() -> None:
    user = User.objects.create_user(username="weather-range-user")
    UserPreferenceService.update_for_user(user, {"weather_location": "上海"})
    provider = RecordingWeatherProvider()

    forecast = WeatherDataService.forecast_for_user(
        user=user,
        start_date=date(2026, 7, 19),
        end_date=date(2026, 7, 25),
        requested_at=datetime(2026, 7, 19, tzinfo=UTC),
        locale="zh-CN",
        provider=provider,
    )

    assert provider.days == 7
    assert len(forecast.daily) == 7
    with pytest.raises(ValueError, match="at most 16"):
        WeatherDataService.forecast_for_user(
            user=user,
            start_date=date(2026, 7, 19),
            end_date=date(2026, 8, 4),
            requested_at=datetime(2026, 7, 19, tzinfo=UTC),
            locale="zh-CN",
            provider=provider,
        )


@pytest.mark.django_db
def test_provider_catalog_api_requires_authentication_and_lists_feeds() -> None:
    client = APIClient()
    assert client.get("/api/v1/providers/catalog/").status_code in {401, 403}

    user = User.objects.create_user(username="provider-catalog-user")
    client.force_authenticate(user=user)
    response = client.get("/api/v1/providers/catalog/")

    assert response.status_code == 200
    assert response.data["weather_provider"] == "open_meteo"
    assert response.data["timezones"] == ["Asia/Shanghai"]
    assert any(item["name"] == "OpenAI News" for item in response.data["news_feeds"])

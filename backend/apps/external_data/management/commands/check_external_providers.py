from datetime import UTC, datetime, timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.external_data.configuration import get_provider_config
from apps.external_data.providers import OpenMeteoWeatherProvider, RssNewsProvider
from common.time import get_timezone


class Command(BaseCommand):
    help = "Check configured weather and news providers without writing business data."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--weather-location", default="")
        parser.add_argument("--language", default="zh-CN")
        parser.add_argument("--topic", action="append", default=[])

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        now = datetime.now(UTC)
        config = get_provider_config()
        self.stdout.write(
            f"weather={config.weather.provider}, news={config.news.provider}, "
            f"configured_feeds={len(config.news.feeds)}"
        )

        location_query = str(options["weather_location"]).strip()
        if location_query:
            weather = OpenMeteoWeatherProvider(config.weather)
            location = weather.resolve_location(location_query, language=str(options["language"]))
            forecast = weather.forecast(
                location,
                start_date=now.astimezone(get_timezone(location.timezone)).date(),
                days=1,
                requested_at=now,
            )
            forecast_day = forecast.daily[0]
            self.stdout.write(
                self.style.SUCCESS(
                    f"weather ok: {location.name} ({location.timezone}), "
                    f"{forecast_day.temperature_min}..{forecast_day.temperature_max}"
                )
            )

        topics = [str(item).strip() for item in options["topic"] if str(item).strip()]
        if topics:
            result = RssNewsProvider(config.news).search(
                topics,
                start_at=now - timedelta(hours=config.news.lookback_hours),
                end_at=now,
                limit=config.news.max_items,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"news checked: selected={len(result.selected_feeds)}, "
                    f"successful={len(result.successful_feeds)}, items={len(result.items)}"
                )
            )
            for warning in result.warnings:
                self.stdout.write(self.style.WARNING(f"warning: {warning}"))
            for news_item in result.items[:5]:
                self.stdout.write(f"- {news_item.publisher}: {news_item.title} ({news_item.url})")

        if not location_query and not topics:
            self.stdout.write("Provide --weather-location and/or one or more --topic values.")

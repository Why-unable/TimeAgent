from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.external_data.configuration import get_provider_config
from apps.external_data.providers.weather import OpenMeteoWeatherProvider
from apps.external_data.serializers import LocationCandidateSerializer, ProviderCatalogSerializer

CHINA_TIMEZONES = ("Asia/Shanghai",)


class ProviderCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ProviderCatalogSerializer)
    def get(self, request: Request) -> Response:
        del request
        config = get_provider_config()
        news_topics = sorted(
            {topic for feed in config.news.feeds for topic in feed.topics}
            | set(config.news.topic_aliases)
        )
        payload = {
            "weather_provider": config.weather.provider,
            "news_provider": config.news.provider,
            "news_feeds": [
                {
                    "name": feed.name,
                    "publisher": feed.publisher,
                    "url": str(feed.url),
                    "topics": feed.topics,
                }
                for feed in config.news.feeds
            ],
            "topic_aliases": config.news.topic_aliases,
            "news_topics": news_topics,
            "timezones": CHINA_TIMEZONES,
            "locales": ["zh-CN", "en-US"],
        }
        return Response(ProviderCatalogSerializer(payload).data)


class LocationSearchView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LocationCandidateSerializer(many=True))
    def get(self, request: Request) -> Response:
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Response([])
        locale = request.query_params.get("locale", "zh-CN")
        try:
            candidates = OpenMeteoWeatherProvider().search_locations(query, language=locale)
        except LookupError:
            return Response([])
        payload = [
            {
                "name": item.name,
                "admin1": item.admin1,
                "country": item.country,
                "timezone": item.timezone,
                "label": " / ".join(
                    part for part in (item.name, item.admin1, item.country) if part
                ),
            }
            for item in candidates
        ]
        return Response(LocationCandidateSerializer(payload, many=True).data)

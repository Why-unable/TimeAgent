from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.external_data.configuration import get_provider_config
from apps.external_data.serializers import ProviderCatalogSerializer


class ProviderCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ProviderCatalogSerializer)
    def get(self, request: Request) -> Response:
        del request
        config = get_provider_config()
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
        }
        return Response(ProviderCatalogSerializer(payload).data)

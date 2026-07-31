import httpx
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.external_data.administrative_areas import administrative_area_options
from apps.external_data.configuration import get_provider_config
from apps.external_data.providers.geocoding import NominatimReverseGeocodingProvider
from apps.external_data.providers.weather import OpenMeteoWeatherProvider
from apps.external_data.schemas import ResolvedLocation
from apps.external_data.serializers import (
    AdministrativeAreaOptionSerializer,
    LocationCandidateSerializer,
    ProviderCatalogSerializer,
)

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
        return Response(
            ProviderCatalogSerializer(
                {
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
            ).data
        )


class LocationSearchView(APIView):
    """Compatibility endpoint for existing saved-place lookups."""

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
        payload = [_location_payload(item) for item in candidates]
        return Response(LocationCandidateSerializer(payload, many=True).data)


class AdministrativeAreaView(APIView):
    """Read-only authoritative catalog for the province/city/district selector."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=AdministrativeAreaOptionSerializer(many=True))
    def get(self, request: Request) -> Response:
        province_code = request.query_params.get("province_code", "").strip()
        city_code = request.query_params.get("city_code", "").strip()
        if city_code and len(city_code) != 6:
            return Response(
                {"detail": "city_code must be a six-digit administrative code"}, status=400
            )
        if province_code and len(province_code) != 6:
            return Response(
                {"detail": "province_code must be a six-digit administrative code"}, status=400
            )
        payload = administrative_area_options(
            province_code=province_code,
            city_code=city_code,
        )
        return Response(AdministrativeAreaOptionSerializer(payload, many=True).data)


class CurrentLocationView(APIView):
    """Reverse an explicitly user-authorized coordinate to a concrete administrative address."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LocationCandidateSerializer)
    def get(self, request: Request) -> Response:
        try:
            latitude = float(request.query_params["latitude"])
            longitude = float(request.query_params["longitude"])
        except (KeyError, TypeError, ValueError):
            return Response({"detail": "latitude and longitude are required"}, status=400)
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return Response({"detail": "coordinates are out of range"}, status=400)

        try:
            address = NominatimReverseGeocodingProvider().reverse(
                latitude=latitude,
                longitude=longitude,
                language=request.query_params.get("locale", "zh-CN"),
            )
        except (httpx.HTTPError, LookupError):
            return Response(
                {
                    "detail": (
                        "Unable to resolve a complete province, city, and district "
                        "from this location"
                    )
                },
                status=422,
            )

        payload = {
            "provider": "device_geolocation",
            "provider_location_id": f"{latitude:.5f},{longitude:.5f}",
            "name": address.district,
            "admin1": address.province,
            "country": address.country or "China",
            "timezone": request.query_params.get("timezone", "Asia/Shanghai"),
            "label": " / ".join((address.province, address.city, address.district)),
            "latitude": latitude,
            "longitude": longitude,
            "province": address.province,
            "city": address.city,
            "district": address.district,
        }
        return Response(LocationCandidateSerializer(payload).data)


class AdministrativeLocationResolveView(APIView):
    """Resolve a selected province/city/district hierarchy into weather coordinates."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LocationCandidateSerializer)
    def get(self, request: Request) -> Response:
        province = request.query_params.get("province", "").strip()
        city = request.query_params.get("city", "").strip()
        district = request.query_params.get("district", "").strip()
        if not (province and city and district):
            return Response({"detail": "province, city, and district are required"}, status=400)

        provider = OpenMeteoWeatherProvider()
        location = None
        # Country is intentionally omitted here. Open-Meteo returns localized
        # country names (for example 中国), so an English "China" qualifier can
        # reject an otherwise exact Chinese administrative match.
        for query in (f"{district}, {city}, {province}", f"{city}, {province}"):
            try:
                location = provider.resolve_location(
                    query,
                    language=request.query_params.get("locale", "zh-CN"),
                )
                break
            except LookupError:
                continue
        if location is None:
            return Response(
                {"detail": "Selected administrative location was not found"}, status=422
            )

        payload = _location_payload(location)
        payload.update(
            {
                "name": district,
                "admin1": province,
                "label": " / ".join((province, city, district)),
                "province": province,
                "city": city,
                "district": district,
            }
        )
        return Response(LocationCandidateSerializer(payload).data)


def _location_payload(item: ResolvedLocation) -> dict[str, object]:
    name = item.name
    admin1 = item.admin1
    country = item.country
    return {
        "provider": "open_meteo",
        "provider_location_id": item.provider_location_id,
        "name": name,
        "admin1": admin1,
        "country": country,
        "timezone": item.timezone,
        "label": " / ".join(part for part in (name, admin1, country) if part),
        "latitude": item.latitude,
        "longitude": item.longitude,
        "province": "",
        "city": "",
        "district": "",
    }

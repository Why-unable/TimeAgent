from typing import Any

from rest_framework import serializers


class ProviderFeedSerializer(serializers.Serializer[Any]):
    name = serializers.CharField()
    publisher = serializers.CharField()
    url = serializers.URLField()
    topics = serializers.ListField(child=serializers.CharField())


class ProviderCatalogSerializer(serializers.Serializer[Any]):
    weather_provider = serializers.CharField()
    news_provider = serializers.CharField()
    news_feeds = ProviderFeedSerializer(many=True)
    topic_aliases = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField())
    )
    news_topics = serializers.ListField(child=serializers.CharField())
    timezones = serializers.ListField(child=serializers.CharField())
    locales = serializers.ListField(child=serializers.CharField())


class LocationCandidateSerializer(serializers.Serializer[Any]):
    provider = serializers.CharField()
    provider_location_id = serializers.CharField()
    name = serializers.CharField()
    admin1 = serializers.CharField()
    country = serializers.CharField()
    timezone = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    province = serializers.CharField(required=False, allow_blank=True, default="")
    city = serializers.CharField(required=False, allow_blank=True, default="")
    district = serializers.CharField(required=False, allow_blank=True, default="")
    adcode = serializers.CharField(required=False, allow_blank=True, default="")


class AdministrativeAreaOptionSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    name = serializers.CharField()

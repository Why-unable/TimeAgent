from typing import Any

from django.db.models import TextChoices
from rest_framework import serializers


class DependencyStatus(TextChoices):
    OK = "ok", "OK"
    ERROR = "error", "Error"


class LiveResponseSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=["alive"])


class DependencyChecksSerializer(serializers.Serializer[Any]):
    database = serializers.ChoiceField(choices=DependencyStatus.choices)
    redis = serializers.ChoiceField(choices=DependencyStatus.choices)


class ReadyResponseSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=["ready", "not_ready"])
    checks = DependencyChecksSerializer()

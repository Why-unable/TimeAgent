from rest_framework import serializers


class AndroidReleaseSerializer(serializers.Serializer[dict[str, object]]):
    version_code = serializers.IntegerField(min_value=1)
    version_name = serializers.CharField()
    download_url = serializers.URLField()
    sha256 = serializers.RegexField(r"^[0-9a-f]{64}$")
    size_bytes = serializers.IntegerField(min_value=1)
    release_notes = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField()
    minimum_supported_version_code = serializers.IntegerField(min_value=1)


class AndroidUpdateResponseSerializer(serializers.Serializer[dict[str, object]]):
    enabled = serializers.BooleanField()
    release = AndroidReleaseSerializer(allow_null=True)

import uuid

from django.db import models


class ExternalNewsItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=64)
    feed_name = models.CharField(max_length=160)
    feed_url = models.URLField(max_length=1000)
    external_id = models.CharField(max_length=1000)
    canonical_url = models.URLField(max_length=2000)
    title = models.CharField(max_length=1000)
    summary = models.TextField(blank=True)
    publisher = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True)
    published_at = models.DateTimeField()
    source_updated_at = models.DateTimeField(null=True, blank=True)
    categories = models.JSONField(default=list)
    content_fingerprint = models.CharField(max_length=64, unique=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "feed_url", "external_id"],
                name="external_news_provider_id_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["-published_at"], name="external_news_published_idx"),
            models.Index(fields=["publisher", "-published_at"], name="external_news_source_idx"),
        ]

    def __str__(self) -> str:
        return self.title

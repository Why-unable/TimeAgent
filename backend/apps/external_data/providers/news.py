from __future__ import annotations

import calendar
import hashlib
import html
import logging
import re
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from html.parser import HTMLParser
from threading import Lock
from time import monotonic, struct_time
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
from django.core.cache import cache

from apps.external_data.configuration import FeedDefinition, NewsProviderConfig, get_provider_config
from apps.external_data.schemas import NewsItemData, NewsSearchResult

_TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_SPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
logger = logging.getLogger(__name__)
_cache_unavailable_until = 0.0
_cache_probe_lock = Lock()


class NewsProvider(Protocol):
    def search(
        self,
        topics: list[str],
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int,
    ) -> NewsSearchResult: ...


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class RssNewsProvider:
    name = "rss"

    def __init__(
        self,
        config: NewsProviderConfig | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config or get_provider_config().news
        self._client = client

    def search(
        self,
        topics: list[str],
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int,
    ) -> NewsSearchResult:
        normalized_topics, keywords = _expand_topics(topics, self.config.topic_aliases)
        directly_matched = [
            feed for feed in self.config.feeds if _feed_matches(feed, normalized_topics, keywords)
        ]
        covered = {
            topic
            for feed in directly_matched
            for topic in normalized_topics
            if topic in {_normalize(item) for item in feed.topics}
        }
        uncovered = sorted(normalized_topics - covered)
        # Unknown topics are search queries, not configuration errors. Search the
        # remaining trusted catalog and retain only entries with keyword matches.
        selected = list(directly_matched)
        if not normalized_topics or uncovered:
            selected.extend(feed for feed in self.config.feeds if feed not in selected)
        directly_matched_names = {feed.name for feed in directly_matched}
        items: list[NewsItemData] = []
        warnings: list[str] = []
        successful_feeds: list[str] = []
        futures: dict[str, Future[list[dict[str, Any]]]] = {}
        if selected:
            with ThreadPoolExecutor(
                max_workers=min(len(selected), self.config.max_concurrent_feeds),
                thread_name_prefix="rss-provider",
            ) as executor:
                futures = {
                    feed.name: executor.submit(self._fetch_entries, feed) for feed in selected
                }
                # Consume in configured order so warnings and equal-score items stay deterministic.
                for feed in selected:
                    try:
                        entries = futures[feed.name].result()
                    except (httpx.HTTPError, ValueError) as exc:
                        warnings.append(f"{feed.name} 暂时不可用（{type(exc).__name__}）。")
                        continue
                    successful_feeds.append(feed.name)
                    for entry in entries[: self.config.max_items_per_feed]:
                        item = _normalize_entry(
                            entry,
                            feed=feed,
                            normalized_topics=normalized_topics,
                            keywords=keywords,
                            require_keyword_match=(
                                bool(normalized_topics) and feed.name not in directly_matched_names
                            ),
                        )
                        if item is not None and start_at <= item.published_at <= end_at:
                            items.append(item)
        items.sort(key=lambda item: (item.score, item.published_at), reverse=True)
        if uncovered:
            warnings.append(f"当前 Feed 目录未覆盖主题：{'、'.join(uncovered)}。")
        return NewsSearchResult(
            items=items[: min(limit, self.config.max_items)],
            warnings=warnings,
            selected_feeds=[feed.name for feed in selected],
            successful_feeds=successful_feeds,
            uncovered_topics=uncovered,
        )

    def _fetch_entries(self, feed: FeedDefinition) -> list[dict[str, Any]]:
        url = str(feed.url)
        cache_key = f"rss-provider:{hashlib.sha256(url.encode()).hexdigest()}"
        cached = _cache_get(cache_key)
        headers = {"Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"}
        if isinstance(cached, dict):
            if cached.get("etag"):
                headers["If-None-Match"] = str(cached["etag"])
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = str(cached["last_modified"])
        response = self._get(url, headers=headers)
        if response.status_code == 304 and isinstance(cached, dict):
            body = bytes(cached.get("body", b""))
        else:
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise ValueError(f"RSS feed exceeds size limit: {feed.name}")
            body = response.content
            _cache_set(
                cache_key,
                {
                    "body": body,
                    "etag": response.headers.get("ETag", ""),
                    "last_modified": response.headers.get("Last-Modified", ""),
                },
                timeout=3600,
            )
        parsed = feedparser.parse(body)
        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
            raise ValueError(f"RSS feed could not be parsed: {feed.name}")
        return [dict(entry) for entry in parsed.entries]

    def _get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        if self._client is not None:
            return self._client.get(url, headers=headers)
        with httpx.Client(
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "TimeAgent/0.1 rss-provider"},
        ) as client:
            return client.get(url, headers=headers)


def canonicalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMETERS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def _normalize(value: str) -> str:
    return _SPACE.sub(" ", _NON_WORD.sub(" ", value.casefold())).strip()


def _expand_topics(topics: list[str], aliases: dict[str, list[str]]) -> tuple[set[str], set[str]]:
    normalized_aliases = {
        _normalize(canonical): {_normalize(canonical), *(_normalize(item) for item in values)}
        for canonical, values in aliases.items()
    }
    requested: set[str] = set()
    keywords: set[str] = set()
    for topic in topics:
        normalized = _normalize(topic)
        if not normalized:
            continue
        canonical = next(
            (name for name, values in normalized_aliases.items() if normalized in values),
            normalized,
        )
        requested.add(canonical)
        keywords.update(normalized_aliases.get(canonical, {normalized}))
    return requested, {item for item in keywords if item}


def _feed_matches(feed: FeedDefinition, topics: set[str], keywords: set[str]) -> bool:
    feed_topics = {_normalize(item) for item in feed.topics}
    return bool(feed_topics & (topics | keywords))


def _normalize_entry(
    entry: dict[str, Any],
    *,
    feed: FeedDefinition,
    normalized_topics: set[str],
    keywords: set[str],
    require_keyword_match: bool = False,
) -> NewsItemData | None:
    title = _plain_text(str(entry.get("title", "")))
    url = canonicalize_url(str(entry.get("link", "")))
    published = _entry_datetime(entry)
    if not title or not url or published is None:
        return None
    summary = _plain_text(str(entry.get("summary") or entry.get("description") or ""))[:4000]
    categories = [
        str(item.get("term", "")).strip()
        for item in entry.get("tags", [])
        if isinstance(item, dict) and str(item.get("term", "")).strip()
    ]
    haystack = _normalize(" ".join([title, summary, *categories]))
    matched = sorted(topic for topic in keywords if topic and topic in haystack)
    if require_keyword_match and not matched:
        return None
    feed_topics = {_normalize(item) for item in feed.topics}
    routed = sorted(normalized_topics & feed_topics)
    score = float(feed.priority) + len(matched) * 20 + len(routed) * 5
    external_id = str(entry.get("id") or entry.get("guid") or url).strip()
    fingerprint_source = f"{_normalize(title)}|{published.date().isoformat()}"
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    return NewsItemData(
        provider="rss",
        feed_name=feed.name,
        feed_url=str(feed.url),
        external_id=external_id,
        title=title,
        summary=summary,
        publisher=feed.publisher,
        author=_plain_text(str(entry.get("author", "")))[:255],
        url=url,
        published_at=published,
        updated_at=_struct_time(entry.get("updated_parsed")),
        categories=categories,
        matched_topics=sorted(set(matched) | set(routed)),
        score=score,
        fingerprint=fingerprint,
        raw_metadata={"language": str(entry.get("language", ""))},
    )


def _entry_datetime(entry: dict[str, Any]) -> datetime | None:
    return _struct_time(entry.get("published_parsed")) or _struct_time(entry.get("updated_parsed"))


def _struct_time(value: object) -> datetime | None:
    if not isinstance(value, struct_time):
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)


def _plain_text(value: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html.unescape(value))
    return _SPACE.sub(" ", " ".join(extractor.parts)).strip()


def _cache_get(key: str) -> object:
    global _cache_unavailable_until
    with _cache_probe_lock:
        if monotonic() < _cache_unavailable_until:
            return None
        try:
            return cache.get(key)
        except Exception as exc:  # Cache is an optimization, never a provider dependency.
            _cache_unavailable_until = monotonic() + 30
            logger.warning("RSS cache read unavailable: %s", type(exc).__name__)
            return None


def _cache_set(key: str, value: object, *, timeout: int) -> None:
    global _cache_unavailable_until
    with _cache_probe_lock:
        if monotonic() < _cache_unavailable_until:
            return
        try:
            cache.set(key, value, timeout=timeout)
        except Exception as exc:  # Cache is an optimization, never a provider dependency.
            _cache_unavailable_until = monotonic() + 30
            logger.warning("RSS cache write unavailable: %s", type(exc).__name__)

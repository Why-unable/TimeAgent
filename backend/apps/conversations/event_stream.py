"""Best-effort Redis Streams bridge for durable AgentEvent records."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from django.conf import settings
from redis import ConnectionPool, Redis
from redis.asyncio import ConnectionPool as AsyncConnectionPool
from redis.asyncio import Redis as AsyncRedis

logger = logging.getLogger(__name__)
STREAM_PREFIX = "timeagent:agent-events:"
STREAM_MAXLEN = 1000
STREAM_TTL_SECONDS = 24 * 60 * 60
_sync_pools: dict[str, ConnectionPool] = {}
_async_pools: dict[str, AsyncConnectionPool] = {}


def _sync_client(url: str) -> Redis:
    pool = _sync_pools.setdefault(
        url,
        ConnectionPool.from_url(
            url, decode_responses=True, socket_connect_timeout=1, socket_timeout=2
        ),
    )
    return Redis(connection_pool=pool)


def _async_client(url: str) -> AsyncRedis:
    pool = _async_pools.setdefault(
        url,
        AsyncConnectionPool.from_url(
            url, decode_responses=True, socket_connect_timeout=1, socket_timeout=12
        ),
    )
    return AsyncRedis(connection_pool=pool)


def stream_key(run_id: UUID | str) -> str:
    return f"{STREAM_PREFIX}{run_id}"


class RedisAgentEventStream:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or settings.AGENT_EVENT_STREAM_REDIS_URL

    def publish(
        self,
        *,
        run_id: UUID | str,
        sequence: int,
        event_type: str,
        payload: dict[str, Any],
        created_at: datetime,
    ) -> bool:
        if not settings.AGENT_EVENT_STREAM_ENABLED:
            return False
        client = _sync_client(self.url)
        key = stream_key(run_id)
        try:
            client.xadd(key, {
                "sequence": str(sequence),
                "event_type": event_type,
                "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                "created_at": created_at.isoformat(),
            }, maxlen=STREAM_MAXLEN, approximate=True)
            client.expire(key, STREAM_TTL_SECONDS)
            return True
        except Exception:
            logger.warning("agent event stream publish failed", extra={"run_id": str(run_id)})
            return False

    async def baseline(self, *, run_id: UUID | str) -> str:
        client = _async_client(self.url)
        entries = await client.xrevrange(stream_key(run_id), count=1)
        return entries[0][0] if entries else "0-0"

    def baseline_sync(self, *, run_id: UUID | str) -> str:
        client = _sync_client(self.url)
        entries = client.xrevrange(stream_key(run_id), count=1)
        return entries[0][0] if entries else "0-0"

    async def read(
        self, *, run_id: UUID | str, after_id: str, block_ms: int = 5000
    ) -> AsyncIterator[dict[str, Any]]:
        client = _async_client(self.url)
        result = await client.xread({stream_key(run_id): after_id}, block=block_ms, count=100)
        for _, entries in result:
            for redis_id, fields in entries:
                yield {
                    "redis_id": redis_id,
                    "sequence": int(fields["sequence"]),
                    "event_type": fields["event_type"],
                    "payload": json.loads(fields["payload"]),
                    "created_at": fields["created_at"],
                }


def publish_agent_event(**kwargs: Any) -> None:
    RedisAgentEventStream().publish(**kwargs)

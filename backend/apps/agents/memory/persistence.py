from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.aio import AsyncPostgresStore

from apps.agents.memory.checkpointer import (
    open_async_postgres_checkpointer,
    open_postgres_checkpointer,
)
from apps.agents.memory.store import open_async_postgres_store, open_postgres_store


@dataclass(frozen=True, slots=True)
class LangGraphPersistence:
    checkpointer: PostgresSaver
    store: PostgresStore


@dataclass(frozen=True, slots=True)
class AsyncLangGraphPersistence:
    checkpointer: AsyncPostgresSaver
    store: AsyncPostgresStore


@contextmanager
def open_langgraph_persistence(
    connection_string: str | None = None,
) -> Iterator[LangGraphPersistence]:
    with (
        open_postgres_checkpointer(connection_string) as checkpointer,
        open_postgres_store(connection_string) as store,
    ):
        yield LangGraphPersistence(checkpointer=checkpointer, store=store)


@asynccontextmanager
async def open_async_langgraph_persistence(
    connection_string: str | None = None,
) -> AsyncIterator[AsyncLangGraphPersistence]:
    async with (
        open_async_postgres_checkpointer(connection_string) as checkpointer,
        open_async_postgres_store(connection_string) as store,
    ):
        yield AsyncLangGraphPersistence(checkpointer=checkpointer, store=store)


def setup_langgraph_persistence(connection_string: str | None = None) -> None:
    """Create or migrate official LangGraph persistence tables."""

    with open_langgraph_persistence(connection_string) as persistence:
        persistence.checkpointer.setup()
        persistence.store.setup()

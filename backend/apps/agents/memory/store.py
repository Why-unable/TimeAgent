from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.aio import AsyncPostgresStore

from apps.agents.memory.connection import (
    get_langgraph_connection_string,
    get_langgraph_store_pool_config,
)


@contextmanager
def open_postgres_store(
    connection_string: str | None = None,
) -> Iterator[PostgresStore]:
    conninfo = connection_string or get_langgraph_connection_string()
    pool_config = get_langgraph_store_pool_config()
    with PostgresStore.from_conn_string(
        conninfo,
        pool_config=pool_config,
    ) as store:
        yield store


@asynccontextmanager
async def open_async_postgres_store(
    connection_string: str | None = None,
) -> AsyncIterator[AsyncPostgresStore]:
    conninfo = connection_string or get_langgraph_connection_string()
    pool_config = get_langgraph_store_pool_config()
    async with AsyncPostgresStore.from_conn_string(
        conninfo,
        pool_config=pool_config,
    ) as store:
        yield store

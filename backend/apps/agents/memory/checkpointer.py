from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from apps.agents.memory.connection import get_langgraph_connection_string


@contextmanager
def open_postgres_checkpointer(
    connection_string: str | None = None,
) -> Iterator[PostgresSaver]:
    conninfo = connection_string or get_langgraph_connection_string()
    with PostgresSaver.from_conn_string(conninfo) as checkpointer:
        yield checkpointer


@asynccontextmanager
async def open_async_postgres_checkpointer(
    connection_string: str | None = None,
) -> AsyncIterator[AsyncPostgresSaver]:
    conninfo = connection_string or get_langgraph_connection_string()
    async with AsyncPostgresSaver.from_conn_string(conninfo) as checkpointer:
        yield checkpointer

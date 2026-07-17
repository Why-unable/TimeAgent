from collections.abc import Mapping
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from langgraph.store.postgres import PoolConfig
from psycopg import ProgrammingError
from psycopg.conninfo import make_conninfo


def get_langgraph_connection_string() -> str:
    """Return validated libpq conninfo without logging credentials."""

    explicit_url = str(getattr(settings, "LANGGRAPH_DATABASE_URL", "")).strip()
    connect_timeout = _positive_int_setting("LANGGRAPH_POSTGRES_CONNECT_TIMEOUT")

    try:
        if explicit_url:
            return make_conninfo(explicit_url, connect_timeout=connect_timeout)

        alias = str(settings.LANGGRAPH_DATABASE_ALIAS)
        database = settings.DATABASES.get(alias)
        if database is None:
            raise ImproperlyConfigured(
                f"LANGGRAPH_DATABASE_ALIAS references unknown database alias: {alias}"
            )
        return _connection_string_from_django_database(database, connect_timeout)
    except (ProgrammingError, TypeError, ValueError) as exc:
        raise ImproperlyConfigured("Invalid LangGraph PostgreSQL connection settings") from exc


def get_langgraph_store_pool_config() -> PoolConfig:
    min_size = _positive_int_setting("LANGGRAPH_STORE_POOL_MIN_SIZE")
    max_size = _positive_int_setting("LANGGRAPH_STORE_POOL_MAX_SIZE")
    if max_size < min_size:
        raise ImproperlyConfigured(
            "LANGGRAPH_STORE_POOL_MAX_SIZE must be greater than or equal to "
            "LANGGRAPH_STORE_POOL_MIN_SIZE"
        )
    return PoolConfig(min_size=min_size, max_size=max_size)


def _connection_string_from_django_database(
    database: Mapping[str, Any],
    connect_timeout: int,
) -> str:
    engine = str(database.get("ENGINE", ""))
    if engine not in {
        "django.db.backends.postgresql",
        "django.db.backends.postgresql_psycopg2",
    }:
        raise ImproperlyConfigured(
            "LangGraph persistence requires PostgreSQL or LANGGRAPH_DATABASE_URL"
        )

    parameters = {
        "dbname": database.get("NAME"),
        "user": database.get("USER"),
        "password": database.get("PASSWORD"),
        "host": database.get("HOST"),
        "port": database.get("PORT"),
        "connect_timeout": connect_timeout,
        "application_name": "time-agent-langgraph",
    }
    return make_conninfo(
        "",
        **{key: str(value) for key, value in parameters.items() if value not in (None, "")},
    )


def _positive_int_setting(name: str) -> int:
    value = int(getattr(settings, name))
    if value < 1:
        raise ImproperlyConfigured(f"{name} must be positive")
    return value

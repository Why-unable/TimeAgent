from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import override_settings
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from psycopg.conninfo import conninfo_to_dict

from apps.agents.memory.checkpointer import open_postgres_checkpointer
from apps.agents.memory.connection import (
    get_langgraph_connection_string,
    get_langgraph_store_pool_config,
)
from apps.agents.memory.persistence import (
    LangGraphPersistence,
    setup_langgraph_persistence,
)
from apps.agents.memory.store import open_postgres_store


@override_settings(
    LANGGRAPH_DATABASE_URL="postgresql://agent:secret@database.example/time_agent",
    LANGGRAPH_POSTGRES_CONNECT_TIMEOUT=7,
)
def test_explicit_langgraph_database_url_is_validated_without_losing_timeout() -> None:
    parameters = conninfo_to_dict(get_langgraph_connection_string())

    assert parameters["dbname"] == "time_agent"
    assert parameters["user"] == "agent"
    assert parameters["password"] == "secret"
    assert parameters["host"] == "database.example"
    assert parameters["connect_timeout"] == "7"


@override_settings(
    LANGGRAPH_DATABASE_URL="",
    LANGGRAPH_DATABASE_ALIAS="langgraph",
    LANGGRAPH_POSTGRES_CONNECT_TIMEOUT=9,
)
def test_django_postgres_settings_are_reused_with_safe_conninfo_quoting() -> None:
    databases = {
        "langgraph": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "agent memory",
            "USER": "agent-user",
            "PASSWORD": "password with spaces",
            "HOST": "postgres",
            "PORT": "5432",
        }
    }

    with patch.object(settings, "DATABASES", databases):
        parameters = conninfo_to_dict(get_langgraph_connection_string())

    assert parameters["dbname"] == "agent memory"
    assert parameters["password"] == "password with spaces"
    assert parameters["application_name"] == "time-agent-langgraph"
    assert parameters["connect_timeout"] == "9"


@override_settings(
    LANGGRAPH_DATABASE_URL="",
    LANGGRAPH_DATABASE_ALIAS="default",
)
def test_non_postgres_database_requires_explicit_langgraph_url() -> None:
    databases = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

    with (
        patch.object(settings, "DATABASES", databases),
        pytest.raises(ImproperlyConfigured, match="requires PostgreSQL"),
    ):
        get_langgraph_connection_string()


@override_settings(
    LANGGRAPH_STORE_POOL_MIN_SIZE=3,
    LANGGRAPH_STORE_POOL_MAX_SIZE=2,
)
def test_store_pool_rejects_inverted_bounds() -> None:
    with pytest.raises(ImproperlyConfigured, match="MAX_SIZE"):
        get_langgraph_store_pool_config()


def test_postgres_resource_factories_forward_configuration_and_close() -> None:
    checkpointer = MagicMock(spec=PostgresSaver)
    checkpointer_context = MagicMock()
    checkpointer_context.__enter__.return_value = checkpointer
    store = MagicMock(spec=PostgresStore)
    store_context = MagicMock()
    store_context.__enter__.return_value = store

    with (
        override_settings(
            LANGGRAPH_STORE_POOL_MIN_SIZE=2,
            LANGGRAPH_STORE_POOL_MAX_SIZE=5,
        ),
        patch.object(
            PostgresSaver,
            "from_conn_string",
            return_value=checkpointer_context,
        ) as saver_factory,
        patch.object(
            PostgresStore,
            "from_conn_string",
            return_value=store_context,
        ) as store_factory,
    ):
        with open_postgres_checkpointer("postgresql://example/checkpoints") as opened:
            assert opened is checkpointer
        with open_postgres_store("postgresql://example/store") as opened_store:
            assert opened_store is store

    saver_factory.assert_called_once_with("postgresql://example/checkpoints")
    store_factory.assert_called_once()
    assert store_factory.call_args.args == ("postgresql://example/store",)
    assert store_factory.call_args.kwargs["pool_config"] == {
        "min_size": 2,
        "max_size": 5,
    }
    checkpointer_context.__exit__.assert_called_once()
    store_context.__exit__.assert_called_once()


def test_setup_runs_official_checkpointer_and_store_migrations() -> None:
    checkpointer = MagicMock(spec=PostgresSaver)
    store = MagicMock(spec=PostgresStore)

    @contextmanager
    def fake_persistence(
        connection_string: str | None = None,
    ) -> Iterator[LangGraphPersistence]:
        assert connection_string == "postgresql://example/time_agent"
        yield LangGraphPersistence(
            checkpointer=cast(PostgresSaver, checkpointer),
            store=cast(PostgresStore, store),
        )

    with patch(
        "apps.agents.memory.persistence.open_langgraph_persistence",
        new=fake_persistence,
    ):
        setup_langgraph_persistence("postgresql://example/time_agent")

    checkpointer.setup.assert_called_once_with()
    store.setup.assert_called_once_with()


def test_setup_langgraph_management_command_reports_success() -> None:
    output = StringIO()

    with patch(
        "apps.agents.management.commands.setup_langgraph.setup_langgraph_persistence"
    ) as setup:
        call_command("setup_langgraph", stdout=output)

    setup.assert_called_once_with()
    assert "LangGraph persistence is ready." in output.getvalue()

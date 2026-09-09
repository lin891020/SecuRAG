"""Start-up really applies the migrations.

Every other test in this suite builds its schema with
``Base.metadata.create_all`` and never touches Alembic, so nothing covered the
path a real boot takes. That path was broken: `alembic/env.py` migrates through
``asyncio.run``, the lifespan called `_run_migrations` directly on the event
loop, and the resulting "asyncio.run() cannot be called from a running event
loop" went into a bare ``except Exception`` that logged a warning. Start-up
migrations never ran, and the only sign was one warning line on an otherwise
healthy boot.

These tests run the real migration scripts against a throwaway SQLite file,
through the real lifespan. SQLite is not Postgres and this does not prove the
DDL is valid there -- every column type these migrations use compiles on both
(`Uuid` to CHAR(32), `JSON`, `DateTime` with `DEFAULT CURRENT_TIMESTAMP`), and
what is being tested is that the migrations run at all.
"""

import asyncio
from functools import partial
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app import main

#: app/main.py -> app/ -> the backend root, which is where alembic/ lives.
BACKEND = Path(main.__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "alembic_version",
    "users",
    "documents",
    "chat_sessions",
    "chat_messages",
    "audit_logs",
}


def _config(database: Path) -> Config:
    """Alembic pointed at a throwaway SQLite file instead of Postgres."""
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database}")
    return config


@pytest.fixture
def stub_llm():
    """The lifespan also builds an LLM provider; that is not what is under test."""
    with patch.object(main, "get_llm_provider", return_value=MagicMock()):
        yield


async def test_lifespan_applies_the_migrations(tmp_path, stub_llm):
    database = tmp_path / "startup.db"

    with patch.object(main, "_run_migrations",
                      partial(main._run_migrations, _config(database))):
        async with main.lifespan(main.app):
            pass

    assert database.exists(), "the lifespan completed without creating a database"
    engine = create_engine(f"sqlite:///{database}")
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert EXPECTED_TABLES <= tables, f"missing {EXPECTED_TABLES - tables}"


async def test_migrations_run_off_the_event_loop(tmp_path, stub_llm):
    """The regression lock.

    `env.py` calls `asyncio.run`, which refuses to start inside a loop that is
    already running. Anything that reaches `_run_migrations` without leaving
    the loop first is the original bug coming back, so assert directly that
    there is no loop where the work happens.
    """
    seen: list[bool] = []
    real = main._run_migrations   # bound before the patch, or record calls itself

    def record(config=None):
        try:
            asyncio.get_running_loop()
            seen.append(True)
        except RuntimeError:
            seen.append(False)
        real(config)

    with patch.object(main, "_run_migrations", partial(record, _config(tmp_path / "t.db"))):
        async with main.lifespan(main.app):
            pass

    assert seen == [False], "migrations ran on the event loop; asyncio.run will refuse"


async def test_a_failed_migration_stops_the_app(stub_llm):
    """Fatal on purpose.

    A backend that starts without its schema answers health checks and then
    fails on the first query that touches a table, several hundred log lines
    away from the cause.
    """
    def boom(config=None):
        raise RuntimeError("relation does not exist")

    with patch.object(main, "_run_migrations", boom):
        with pytest.raises(RuntimeError, match="relation does not exist"):
            async with main.lifespan(main.app):
                pass

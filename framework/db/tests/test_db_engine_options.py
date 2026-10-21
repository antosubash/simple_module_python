"""Driver timeout mappings and application engine wiring (#531)."""

import pytest
from simple_module_db.engine_options import connect_args
from simple_module_db.session import init_db
from simple_module_test.database import database_url_for_tests
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool, StaticPool


@pytest.mark.parametrize("driver", ["psycopg2", "psycopg"])
def test_libpq(driver):
    assert connect_args(
        f"postgresql+{driver}://localhost/db",
        connect_timeout=7,
        statement_timeout_ms=1000,
        idle_in_tx_timeout_ms=2000,
    ) == {
        "connect_timeout": 7,
        "options": "-c statement_timeout=1000 -c idle_in_transaction_session_timeout=2000",
    }


def test_asyncpg():
    assert connect_args(
        "postgresql+asyncpg://localhost/db",
        connect_timeout=7,
        statement_timeout_ms=1000,
        idle_in_tx_timeout_ms=2000,
    ) == {
        "timeout": 7,
        "server_settings": {
            "statement_timeout": "1000",
            "idle_in_transaction_session_timeout": "2000",
        },
    }


@pytest.mark.parametrize("driver", ["asyncpg", "psycopg2", "psycopg"])
def test_zero_omits_keys(driver):
    assert connect_args(f"postgresql+{driver}://localhost/db", connect_timeout=0) == {}


def test_sqlite():
    assert connect_args("sqlite+aiosqlite://", statement_timeout_ms=1000) == {}


async def test_init_db_options():
    state = init_db(
        "postgresql+asyncpg://localhost/db",
        pool_timeout=17,
        connect_timeout=4,
        statement_timeout_ms=123,
        idle_in_tx_timeout_ms=456,
    )
    assert state.engine.pool.timeout() == 17
    captured = {}

    @event.listens_for(state.engine.sync_engine, "do_connect")
    def capture(dialect, record, args, kwargs):
        captured.update(kwargs)
        raise RuntimeError("captured")

    try:
        with pytest.raises(RuntimeError, match="captured"):
            async with state.engine.connect():
                pass
        assert captured["timeout"] == 4
        assert captured["server_settings"] == {
            "statement_timeout": "123",
            "idle_in_transaction_session_timeout": "456",
        }
    finally:
        await state.engine.dispose()


async def test_sqlite_ignores_pool_timeout():
    state = init_db("sqlite+aiosqlite://", pool_timeout=17, statement_timeout_ms=1000)
    try:
        assert isinstance(state.engine.pool, StaticPool)
    finally:
        await state.engine.dispose()


@pytest.mark.postgres
async def test_web_statement_timeout():
    state = init_db(
        database_url_for_tests(),
        statement_timeout_ms=1000,
        poolclass=NullPool,
    )
    try:
        async with state.engine.connect() as connection:
            with pytest.raises(DBAPIError, match="statement timeout"):
                await connection.execute(text("SELECT pg_sleep(2)"))
    finally:
        await state.engine.dispose()

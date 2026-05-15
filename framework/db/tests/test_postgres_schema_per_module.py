"""End-to-end Postgres schema-per-module test (skipped without a PG URL).

CLAUDE.md promises that on Postgres each module's tables live in their own
schema (``orders.<table>``). All of the existing DB test suites run against
SQLite where the convention is to prefix the table name instead, so the
Postgres branch of ``create_module_base`` is exercised only by the
diagnostics tests indirectly.

This test runs only if ``SM_POSTGRES_TEST_URL`` is set, so CI on machines
without a Postgres available is a clean skip rather than a failure.
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.provider import DatabaseProvider
from simple_module_db.session import init_db
from sqlalchemy import text
from sqlmodel import Field

if TYPE_CHECKING:
    pass


_PG_URL = os.environ.get("SM_POSTGRES_TEST_URL")
_PG_SKIP_REASON = "Set SM_POSTGRES_TEST_URL=postgresql+asyncpg://... to run Postgres tests"


@pytest.mark.anyio
@pytest.mark.skipif(not _PG_URL, reason=_PG_SKIP_REASON)
async def test_module_tables_isolated_per_schema():
    """Two modules' tables must live in separate schemas with the same suffix.

    Without per-schema isolation, ``orders.product`` and ``billing.product``
    would collide. We create two ad-hoc module bases with the same suffix,
    insert rows in each, and confirm the rows are not visible cross-schema.
    """
    schema_a = f"sm_test_a_{uuid.uuid4().hex[:8]}"
    schema_b = f"sm_test_b_{uuid.uuid4().hex[:8]}"

    base_a = create_module_base(schema_a, provider=DatabaseProvider.POSTGRESQL)
    base_b = create_module_base(schema_b, provider=DatabaseProvider.POSTGRESQL)

    class _ProductA(base_a, table=True):  # type: ignore[call-arg,misc]  # ty: ignore[unsupported-base]
        __tablename__ = "product"
        id: int | None = Field(default=None, primary_key=True)
        name: str = Field(max_length=100)

    class _ProductB(base_b, table=True):  # type: ignore[call-arg,misc]  # ty: ignore[unsupported-base]
        __tablename__ = "product"
        id: int | None = Field(default=None, primary_key=True)
        name: str = Field(max_length=100)

    db_state = init_db(_PG_URL)  # type: ignore[arg-type]
    try:
        async with db_state.engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_a}"'))
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_b}"'))
            await conn.run_sync(base_a.metadata.create_all)
            await conn.run_sync(base_b.metadata.create_all)

        async with db_state.session_factory() as session:
            session.add(_ProductA(name="a-thing"))
            session.add(_ProductB(name="b-thing"))
            await session.commit()

            # Raw SQL to bypass ORM tenant filters and confirm schema isolation.
            in_a = (
                (await session.execute(text(f'SELECT name FROM "{schema_a}"."product"')))
                .scalars()
                .all()
            )
            in_b = (
                (await session.execute(text(f'SELECT name FROM "{schema_b}"."product"')))
                .scalars()
                .all()
            )
            assert in_a == ["a-thing"]
            assert in_b == ["b-thing"]

        # Teardown
        async with db_state.engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema_a}" CASCADE'))
            await conn.execute(text(f'DROP SCHEMA "{schema_b}" CASCADE'))
    finally:
        await db_state.engine.dispose()


def test_module_metadata_has_schema_set():
    """Static check: a base created with provider=POSTGRESQL stamps a schema.

    Runs without a live Postgres so we still get coverage of the metadata
    branch on every test run.
    """
    base = create_module_base("isolated_smoke", provider=DatabaseProvider.POSTGRESQL)
    assert base.metadata.schema == "isolated_smoke"


def test_module_metadata_has_no_schema_for_sqlite():
    base = create_module_base("flat_smoke", provider=DatabaseProvider.SQLITE)
    assert base.metadata.schema is None

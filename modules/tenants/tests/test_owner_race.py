"""Concurrent writes that must resolve to one winner and a clean refusal.

Runs on a file-backed SQLite database with the real connection pool, so the
two sessions really are two connections — and on Postgres too when
``SM_TEST_DATABASE_URL`` points at one. The ``app`` fixture's in-memory
database shares one connection between sessions, which cannot model two
concurrent transactions at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from simple_module_db.listeners import register_listeners
from simple_module_db.session import DatabaseState, init_db
from simple_module_test.database import (
    database_url_for_tests,
    init_db_kwargs,
    is_sqlite,
    reset_schema,
)
from tenants.constants import MembershipRole
from tenants.contracts.schemas import TenantCreate
from tenants.errors import TenantError
from tenants.models import Base
from tenants.service import TenantService


def _backends() -> list[str]:
    backends = ["sqlite-file"]
    if not is_sqlite(database_url_for_tests()):
        backends.append("postgres")
    return backends


@asynccontextmanager
async def _database(tmp_path, backend: str) -> AsyncIterator[DatabaseState]:
    if backend == "postgres":
        url = database_url_for_tests()
        state = init_db(url, **init_db_kwargs(url))
        await reset_schema(state.engine)
    else:
        state = init_db(f"sqlite+aiosqlite:///{tmp_path}/race.db")
    register_listeners(state)
    try:
        async with state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield state
    finally:
        await state.engine.dispose()


@pytest.mark.parametrize("backend", _backends())
async def test_concurrent_creates_with_one_slug_give_one_tenant(tmp_path, backend: str):
    """The loser of a slug race gets ``slug_taken`` (a 409), not a 500."""
    async with _database(tmp_path, backend) as state:

        async def create(owner: str) -> str:
            async with state.session_factory() as db:
                try:
                    await TenantService(db).create_tenant(
                        TenantCreate(name=owner, slug="dupe"), owner_user_id=owner
                    )
                    await db.commit()
                    return "ok"
                except TenantError as exc:
                    await db.rollback()
                    return exc.code

        outcomes = await asyncio.gather(create("a"), create("b"))
        assert sorted(outcomes) == ["ok", "slug_taken"]


@pytest.mark.parametrize("backend", _backends())
async def test_concurrent_demotion_of_the_two_owners_keeps_one(tmp_path, backend: str):
    async with _database(tmp_path, backend) as state:
        async with state.session_factory() as db:
            service = TenantService(db)
            tenant = await service.create_tenant(TenantCreate(name="Race"), owner_user_id="a")
            await service.add_member(tenant.id, "b", MembershipRole.OWNER, seat_reserved=True)
            await db.commit()

        async def demote(user_id: str) -> str:
            async with state.session_factory() as db:
                try:
                    await TenantService(db).change_role(
                        tenant.id, user_id, MembershipRole.ADMIN, actor_role=MembershipRole.OWNER
                    )
                    await db.commit()
                    return "ok"
                except TenantError as exc:
                    await db.rollback()
                    return exc.code

        outcomes = await asyncio.gather(demote("a"), demote("b"))
        async with state.session_factory() as db:
            owners = await TenantService(db)._owner_count(tenant.id)
        assert sorted(outcomes) == ["last_owner", "ok"]
        assert owners == 1

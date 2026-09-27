"""Two owners demoting each other at once must leave one owner.

Runs on a file-backed SQLite database with the real connection pool, so the
two sessions really are two connections. The ``app`` fixture's in-memory
database shares one connection between sessions, which cannot model two
concurrent transactions at all.
"""

from __future__ import annotations

import asyncio

from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from tenants.constants import MembershipRole
from tenants.contracts.schemas import TenantCreate
from tenants.errors import TenantError
from tenants.models import Base
from tenants.service import TenantService


async def test_concurrent_demotion_of_the_two_owners_keeps_one(tmp_path):
    state = init_db(f"sqlite+aiosqlite:///{tmp_path}/race.db")
    register_listeners(state)
    try:
        async with state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
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
    finally:
        await state.engine.dispose()

"""Seat admission uses the SQLite writer lock, including stale snapshots (#753)."""

import asyncio
from sqlite3 import SQLITE_BUSY_SNAPSHOT

import pytest
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from sqlalchemy import event, func, select, text
from tenants.contracts.entitlements import EntitlementExceededError
from tenants.contracts.schemas import InvitationCreate, TenantCreate
from tenants.core.constants import MembershipRole
from tenants.core.errors import TenantError
from tenants.core.service import TenantService
from tenants.invitations.service import InvitationService
from tenants.models import Base, Invitation, Membership


class TwoSeats:
    async def limit(self, tenant_id, key):
        return 2

    async def has_feature(self, tenant_id, key):
        return True


@pytest.mark.parametrize("invitation", [False, True])
@pytest.mark.parametrize("snapshot", [False, True])
async def test_concurrent_seat_admission_stays_within_limit(tmp_path, invitation, snapshot):
    url = f"sqlite+aiosqlite:///{tmp_path}/seats.db"
    first, second = init_db(url), init_db(url)
    for state in (first, second):
        register_listeners(state)
    writing = asyncio.Event()

    @event.listens_for(second.engine.sync_engine, "before_cursor_execute")
    def attempted_write(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writing.set()

    async def admit(db, user):
        tenants = TenantService(db, entitlements=TwoSeats())
        if invitation:
            return await InvitationService(tenants, ttl_hours=24).create(
                tenant_id, InvitationCreate(email=f"{user}@example.com"), base_url=""
            )
        return await tenants.add_member(tenant_id, user, MembershipRole.MEMBER)

    try:
        async with first.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with first.session_factory() as db:
            tenant = await TenantService(db).create_tenant(
                TenantCreate(name="Seats"), owner_user_id="owner"
            )
            tenant_id = tenant.id
            await db.commit()
        async with first.session_factory() as a, second.session_factory() as b:
            if snapshot:
                await b.execute(text("BEGIN"))
                await b.scalar(select(func.count()).select_from(Membership))
            await admit(a, "first")
            if snapshot:
                await a.commit()

            async def contender():
                try:
                    await admit(b, "second")
                    await b.commit()
                except EntitlementExceededError:
                    await b.rollback()
                    return "refused"
                except TenantError as exc:
                    assert exc.status_code == 409
                    if snapshot:
                        assert exc.__cause__.orig.sqlite_errorcode == SQLITE_BUSY_SNAPSHOT
                    await b.rollback()
                    return "refused"
                return "admitted"

            task = asyncio.create_task(contender())
            try:
                await asyncio.wait_for(writing.wait(), 5)
                await a.commit()
                assert await asyncio.wait_for(task, 5) == "refused"
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            members = await b.scalar(select(func.count()).select_from(Membership))
            invites = await b.scalar(select(func.count()).select_from(Invitation))
            assert members + invites == 2
    finally:
        await first.engine.dispose()
        await second.engine.dispose()

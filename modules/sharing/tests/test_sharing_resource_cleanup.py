"""Resource owners can remove shares transactionally in the bound tenant (#683)."""

import pytest
from sharing import contracts
from sharing.models import ResourceShare
from simple_module_db import TenantIsolationError, all_tenants, tenant_context
from sqlmodel import select


async def _seed(db):
    for tenant in ("acme", "other"):
        with tenant_context(tenant):
            for kind, resource in (
                ("test.note", "note"),
                ("test.note", "next"),
                ("test.other", "note"),
            ):
                for subject in ("reader", "editor"):
                    db.add(
                        ResourceShare(
                            resource_type=kind,
                            resource_id=resource,
                            subject_id=subject,
                            role="view",
                            granted_by="owner",
                        )
                    )
            await db.flush()
    await db.commit()


@pytest.mark.parametrize("resource_ids", ["note", ["note", "next"], []])
async def test_forget_resource_is_scoped_idempotent_and_transactional(db_session, resource_ids):
    forget = contracts.forget_resource
    await _seed(db_session)
    ids = resource_ids if isinstance(resource_ids, str) else list(resource_ids)
    count = 2 if ids == "note" else 2 * len(ids)
    with tenant_context("acme"):
        await forget(db_session, "test.note", ids)
    with all_tenants():
        assert len((await db_session.execute(select(ResourceShare))).scalars().all()) == 12 - count
    await db_session.rollback()
    with all_tenants():
        assert len((await db_session.execute(select(ResourceShare))).scalars().all()) == 12
    with tenant_context("acme"):
        await forget(db_session, "test.note", ids)
        await forget(db_session, "test.note", ids)
    await db_session.commit()
    with all_tenants():
        rows = (await db_session.execute(select(ResourceShare))).scalars().all()
    assert len(rows) == 12 - count
    assert sum(row.tenant_id == "other" for row in rows) == 6
    assert sum(row.resource_type == "test.other" for row in rows) == 4
    removed = {ids} if isinstance(ids, str) else set(ids)
    assert not any(
        row.tenant_id == "acme" and row.resource_type == "test.note" and row.resource_id in removed
        for row in rows
    )


async def test_forget_resource_fails_closed_without_tenant(db_state, db_session):
    db_state.tenant_strict = True
    with pytest.raises(TenantIsolationError):
        await contracts.forget_resource(db_session, "test.note", "note")


async def test_forget_resource_accepts_one_shot_iterables(db_session):
    await _seed(db_session)
    with tenant_context("acme"):
        await contracts.forget_resource(db_session, "test.note", iter(["note", "next"]))
        rows = (await db_session.execute(select(ResourceShare))).scalars().all()
    assert [(row.resource_type, row.resource_id) for row in rows] == [
        ("test.other", "note"),
        ("test.other", "note"),
    ]

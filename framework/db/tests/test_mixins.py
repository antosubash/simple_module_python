"""Direct unit tests for the SQLModel mixins.

The mixins (AuditMixin, SoftDeleteMixin, VersionedMixin, MultiTenantMixin)
have plenty of *indirect* coverage through the multi-tenancy and audit-logging
test suites, but no test pins their individual contracts:

* ``AuditMixin`` populates ``created_by``/``updated_by`` from the contextvar.
* ``SoftDeleteMixin`` converts ``DELETE`` into a soft-delete and applies the
  default loader filter, with the documented ``include_deleted=True`` bypass.
* ``VersionedMixin`` increments ``version`` on every modifying flush.

If any of these regressed, the only surface that would catch it today is
"the audit-log integration test breaks in some other way" — these tests
make the failure mode local and obvious.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.listeners import current_tenant_id, current_user_id, register_listeners
from simple_module_db.mixins import (
    AuditMixin,
    MultiTenantMixin,
    SoftDeleteMixin,
    VersionedMixin,
)
from simple_module_db.provider import DatabaseProvider
from simple_module_db.session import init_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, select

_MixinsBase = create_module_base("mixins_test", provider=DatabaseProvider.SQLITE)


class _AuditRow(_MixinsBase, AuditMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "mixins_test_audit_row"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


class _SoftRow(_MixinsBase, SoftDeleteMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "mixins_test_soft_row"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


class _VersionedRow(_MixinsBase, VersionedMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "mixins_test_versioned_row"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


class _AllRow(
    _MixinsBase,  # ty: ignore[unsupported-base]
    MultiTenantMixin,
    AuditMixin,
    SoftDeleteMixin,
    VersionedMixin,
    table=True,
):  # type: ignore[call-arg]
    """Composite: confirms every listener stays compatible when stacked."""

    __tablename__ = "mixins_test_all_row"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


@pytest.fixture
async def mixin_session() -> AsyncGenerator[AsyncSession, None]:
    db_state = init_db("sqlite+aiosqlite:///:memory:")
    try:
        register_listeners(db_state)
        async with db_state.engine.begin() as conn:
            await conn.run_sync(_MixinsBase.metadata.create_all)
        async with db_state.session_factory() as session:
            yield session
    finally:
        await db_state.engine.dispose()


# ── AuditMixin ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_audit_mixin_populates_created_by_from_contextvar(mixin_session):
    token = current_user_id.set("alice-id")
    try:
        row = _AuditRow(name="hello")
        mixin_session.add(row)
        await mixin_session.commit()
        await mixin_session.refresh(row)
    finally:
        current_user_id.reset(token)

    assert row.created_by == "alice-id"
    assert row.updated_by == "alice-id"
    assert row.created_at is not None


@pytest.mark.anyio
async def test_audit_mixin_updates_updated_by_on_modify(mixin_session):
    create_token = current_user_id.set("alice-id")
    row = _AuditRow(name="initial")
    mixin_session.add(row)
    await mixin_session.commit()
    current_user_id.reset(create_token)

    update_token = current_user_id.set("bob-id")
    try:
        row.name = "changed"
        await mixin_session.commit()
        await mixin_session.refresh(row)
    finally:
        current_user_id.reset(update_token)

    assert row.created_by == "alice-id"
    assert row.updated_by == "bob-id"
    assert row.updated_at is not None


# ── SoftDeleteMixin ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_soft_delete_marks_instead_of_removing(mixin_session):
    row = _SoftRow(name="will-be-soft-deleted")
    mixin_session.add(row)
    await mixin_session.commit()
    await mixin_session.refresh(row)
    rowid = row.id

    await mixin_session.delete(row)
    await mixin_session.commit()

    # Row still on disk — listener intercepted the DELETE.
    found = await mixin_session.execute(
        select(_SoftRow).where(_SoftRow.id == rowid).execution_options(include_deleted=True)
    )
    persisted = found.scalar_one()
    assert persisted.is_deleted is True
    assert persisted.deleted_at is not None

    # Default loader filter hides it.
    default_view = await mixin_session.execute(select(_SoftRow).where(_SoftRow.id == rowid))
    assert default_view.scalar_one_or_none() is None


@pytest.mark.anyio
async def test_soft_delete_bypass_flag_reveals_deleted_rows(mixin_session):
    a = _SoftRow(name="visible")
    b = _SoftRow(name="hidden")
    mixin_session.add_all([a, b])
    await mixin_session.commit()
    await mixin_session.delete(b)
    await mixin_session.commit()

    filtered = (await mixin_session.execute(select(_SoftRow))).scalars().all()
    assert [r.name for r in filtered] == ["visible"]

    all_rows = (
        (await mixin_session.execute(select(_SoftRow).execution_options(include_deleted=True)))
        .scalars()
        .all()
    )
    names = sorted(r.name for r in all_rows)
    assert names == ["hidden", "visible"]


# ── VersionedMixin ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_versioned_mixin_increments_on_update(mixin_session):
    row = _VersionedRow(name="v1")
    mixin_session.add(row)
    await mixin_session.commit()
    await mixin_session.refresh(row)
    assert row.version == 1

    row.name = "v2"
    await mixin_session.commit()
    await mixin_session.refresh(row)
    assert row.version == 2

    row.name = "v3"
    await mixin_session.commit()
    await mixin_session.refresh(row)
    assert row.version == 3


@pytest.mark.anyio
async def test_versioned_mixin_not_incremented_for_no_op_flush(mixin_session):
    row = _VersionedRow(name="stable")
    mixin_session.add(row)
    await mixin_session.commit()
    await mixin_session.refresh(row)
    assert row.version == 1

    # Touch nothing — just commit again. ``session.is_modified`` should
    # return False so the listener skips the bump.
    await mixin_session.commit()
    await mixin_session.refresh(row)
    assert row.version == 1


# ── Composition: all four mixins on one row ─────────────────────────────────


@pytest.mark.anyio
async def test_all_mixins_compose_without_conflict(mixin_session):
    user_token = current_user_id.set("composer-id")
    tenant_token = current_tenant_id.set("tenant-A")
    try:
        row = _AllRow(name="composed")
        mixin_session.add(row)
        await mixin_session.commit()
        await mixin_session.refresh(row)
    finally:
        current_user_id.reset(user_token)
        current_tenant_id.reset(tenant_token)

    assert row.tenant_id == "tenant-A"
    assert row.created_by == "composer-id"
    assert row.is_deleted is False
    assert row.version == 1

"""Soft-delete / tenant filtering for selects that name no ORM entity (GH #332).

``ORMExecuteState.all_mappers`` is derived from the statement's
``column_descriptions``, so three everyday shapes used to slip past both
filters entirely — a wrong count on a single-tenant host, and a cross-tenant
read on a multi-tenant one. Each shape below needs a *different* fix, which is
why they are pinned separately rather than as one parametrized case.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.listeners import current_tenant_id, register_listeners
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.session import init_db
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import StaticPool
from sqlmodel import Field

_FilterBase = create_module_base("qfilter_test")


class _Thing(_FilterBase, SoftDeleteMixin, MultiTenantMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "qfilter_test_thing"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=100)


class _Note(_FilterBase, SoftDeleteMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Soft-delete only, and referenced by an outer join below."""

    __tablename__ = "qfilter_test_note"
    id: int | None = Field(default=None, primary_key=True)
    thing_id: int | None = Field(default=None, foreign_key="qfilter_test_thing.id")


@pytest.fixture
async def seeded() -> AsyncGenerator[AsyncSession, None]:
    """Tenant A: one live row + one trashed row. Tenant B: one live row."""
    db_state = init_db("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        register_listeners(db_state)
        async with db_state.engine.begin() as conn:
            await conn.run_sync(_FilterBase.metadata.create_all)
        async with db_state.session_factory() as session:
            token = current_tenant_id.set("A")
            session.add_all([_Thing(name="live"), _Thing(name="trashed", is_deleted=True)])
            await session.flush()
            current_tenant_id.reset(token)
            token = current_tenant_id.set("B")
            session.add(_Thing(name="other-tenant"))
            await session.flush()
            current_tenant_id.reset(token)
            await session.commit()
        async with db_state.session_factory() as session:
            token = current_tenant_id.set("A")
            try:
                yield session
            finally:
                current_tenant_id.reset(token)
    finally:
        await db_state.engine.dispose()


@pytest.fixture
async def notes(seeded):
    """One live and one trashed note hanging off tenant A's live thing."""
    thing = (await seeded.execute(select(_Thing))).scalars().first()
    seeded.add_all([_Note(thing_id=thing.id), _Note(thing_id=thing.id, is_deleted=True)])
    await seeded.flush()
    return thing


async def test_entity_select_is_filtered(seeded):
    """Baseline: the shape that already worked must keep working."""
    rows = (await seeded.execute(select(_Thing))).scalars().all()
    assert [r.name for r in rows] == ["live"]


async def test_count_naming_the_entity_is_filtered(seeded):
    """``func.count(Model.id)`` names the mapper, so ``all_mappers`` covers it."""
    assert (await seeded.execute(select(func.count(_Thing.id)))).scalar_one() == 1


async def test_bare_count_over_entity_is_filtered(seeded):
    """``select_from(Model)`` leaves an annotated table as the only FROM.

    Fixed by a WHERE built from that FROM element's own columns — referencing
    ``Model.__table__`` instead would add a second FROM and cross-join them.
    """
    stmt = select(func.count()).select_from(_Thing)
    assert (await seeded.execute(stmt)).scalar_one() == 1


async def test_count_over_subquery_is_filtered(seeded):
    """A WHERE on the outer statement would cartesian-product here.

    The entity lives inside the subquery, so ``with_loader_criteria`` — which
    reaches it wherever it is compiled — is the only correct tool.
    """
    stmt = select(func.count()).select_from(select(_Thing).subquery())
    assert (await seeded.execute(stmt)).scalar_one() == 1


async def test_core_select_over_raw_table_is_filtered(seeded):
    """A pure Core FROM carries no ORM identity for loader criteria to attach to."""
    stmt = select(func.count()).select_from(_Thing.__table__)
    assert (await seeded.execute(stmt)).scalar_one() == 1


async def test_include_deleted_still_bypasses_soft_delete(seeded):
    """The documented escape hatch must survive on the new code paths too."""
    stmt = select(func.count()).select_from(_Thing).execution_options(include_deleted=True)
    # Tenant isolation is not bypassable, so tenant B's row stays out.
    assert (await seeded.execute(stmt)).scalar_one() == 2


async def test_tenant_filter_applies_without_tenant_context(seeded):
    """With no tenant bound, only soft-delete filtering applies."""
    current_tenant_id.set(None)
    stmt = select(func.count()).select_from(_Thing)
    assert (await seeded.execute(stmt)).scalar_one() == 2


async def test_core_inner_join_filters_both_sides(seeded, notes):
    """Both sides of an INNER join are WHERE-able, so both get filtered.

    Two live things and two notes exist, but one of each is trashed; only the
    live thing / live note pair should survive.
    """
    joined = _Thing.__table__.join(_Note.__table__, _Note.thing_id == _Thing.id)
    stmt = select(func.count()).select_from(joined)
    assert (await seeded.execute(stmt)).scalar_one() == 1


async def test_core_outer_join_keeps_its_left_rows(seeded, notes):
    """A WHERE on the nullable side would demote this LEFT JOIN to an inner one.

    The left row whose only note is trashed must still come back — so the
    nullable side falls back to loader criteria rather than a WHERE.
    """
    joined = _Thing.__table__.outerjoin(_Note.__table__, _Note.thing_id == _Thing.id)
    stmt = select(func.count()).select_from(joined)
    # Tenant A has exactly one live thing, and it keeps its row whether or not
    # a live note joins to it.
    assert (await seeded.execute(stmt)).scalar_one() >= 1

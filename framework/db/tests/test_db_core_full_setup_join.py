"""FULL ``.outerjoin(..., full=True)`` steps keep both sides (#506 review).

A FULL join preserves its left side too, so that side's tenant predicate
cannot sit in a plain ``WHERE``: it would drop the rows the join pads on
the left and turn the FULL join into a RIGHT one. The expected rows are
what filtering both inputs to tenant A first would give; tenant B's rows
must never appear, matched or not.

Tenant A: parents ``a1`` (1), ``a2`` (2); children 1 → ``a1`` and 2 →
nothing. Tenant B: parent ``b`` (3) and child 3 → ``a1`` (the leak probe),
child 4 → ``b``. Child 5 (tenant A) → ``b``: matched only across tenants,
so it must come back unmatched.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from _models import _tenant_session
from simple_module_db.base import create_module_base
from simple_module_db.mixins import MultiTenantMixin
from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
from simple_module_db.tenancy import TenantIsolationError, current_tenant_id, tenant_context
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field

_Base = create_module_base("cfull")


class Parent(_Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "cfull_parent"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=50)


class Child(_Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "cfull_child"
    id: int | None = Field(default=None, primary_key=True)
    parent_id: int | None = Field(default=None, foreign_key="cfull_parent.id")


parent, child = Parent.__table__, Child.__table__
_ON = child.c.parent_id == parent.c.id
_FULL = [("a1", 1), ("a2", None), (None, 2), (None, 5)]


async def _seed(session: AsyncSession) -> None:
    with tenant_context("A"):
        session.add_all([Parent(id=1, name="a1"), Parent(id=2, name="a2")])
        await session.flush()
    with tenant_context("B"):
        session.add(Parent(id=3, name="b"))
        await session.flush()
        session.add_all([Child(id=3, parent_id=1), Child(id=4, parent_id=3)])
        await session.flush()
    with tenant_context("A"):
        session.add_all([Child(id=1, parent_id=1), Child(id=2), Child(id=5, parent_id=3)])
        await session.flush()
    await session.commit()


@pytest.fixture
async def as_a() -> AsyncGenerator[AsyncSession, None]:
    async for session in _tenant_session(_Base.metadata, strict=False, seed=_seed):
        token = current_tenant_id.set("A")
        try:
            yield session
        finally:
            current_tenant_id.reset(token)


async def _rows(session: AsyncSession, stmt) -> list[tuple]:
    return sorted((tuple(r) for r in (await session.execute(stmt)).all()), key=repr)


_COLS = (parent.c.name, child.c.id)


async def test_full_step_from_columns_clause_keeps_left_padding(as_a):
    stmt = select(*_COLS).outerjoin(child, _ON, full=True)
    assert await _rows(as_a, stmt) == sorted(_FULL, key=repr)


async def test_full_step_after_select_from(as_a):
    stmt = select(*_COLS).select_from(parent).outerjoin(child, _ON, full=True)
    assert await _rows(as_a, stmt) == sorted(_FULL, key=repr)


async def test_full_step_without_onclause_uses_inferred_on(as_a):
    stmt = select(*_COLS).select_from(parent).outerjoin(child, full=True)
    assert await _rows(as_a, stmt) == sorted(_FULL, key=repr)


async def test_full_step_after_inner_step(as_a):
    other = parent.alias("p2")
    stmt = (
        select(*_COLS)
        .select_from(parent)
        .join(other, other.c.id == parent.c.id)
        .outerjoin(child, _ON, full=True)
    )
    assert await _rows(as_a, stmt) == sorted(_FULL, key=repr)


async def test_left_step_without_onclause_stays_outer(as_a):
    stmt = select(*_COLS).select_from(parent).outerjoin(child)
    assert await _rows(as_a, stmt) == [("a1", 1), ("a2", None)]


async def test_all_tenants_sees_every_row(as_a):
    stmt = select(*_COLS).outerjoin(child, _ON, full=True).execution_options(all_tenants=True)
    rows = await _rows(as_a, stmt)
    assert ("a1", 3) in rows and ("b", 4) in rows and ("b", 5) in rows


async def test_strict_without_tenant_refuses(as_a):
    bind_engine_policy(as_a.bind.sync_engine, EngineTenancy(tenant_strict=True))
    current_tenant_id.set(None)
    with pytest.raises(TenantIsolationError):
        await as_a.execute(select(*_COLS).outerjoin(child, _ON, full=True))

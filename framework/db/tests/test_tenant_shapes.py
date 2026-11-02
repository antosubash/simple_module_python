"""#332: tenant scoping reaches joins, subqueries, counts and Core statements."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_db import (
    MissingTenantError,
    MultiTenantMixin,
    create_module_base,
    tenant_context,
)
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from simple_module_test.database import database_url_for_tests, init_db_kwargs, reset_schema
from sqlalchemy import delete, exists, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field

_URL = database_url_for_tests()

_Base = create_module_base("shapes")


class _Project(_Base, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "shapes_project"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=20)


class _Doc(_Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "shapes_doc"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=20)
    project_id: int | None = Field(default=None, foreign_key="shapes_project.id")


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    state = init_db(_URL, **init_db_kwargs(_URL))
    state.tenant_strict = True
    register_listeners(state)
    await reset_schema(state.engine)
    async with state.engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    async with state.session_factory() as session:
        session.add_all([_Project(id=1, name="p1"), _Project(id=2, name="p2")])
        await session.flush()  # parents first: no relationship() orders the flush
        for tenant, project in (("a", 1), ("b", 2)):
            with tenant_context(tenant):
                session.add(_Doc(name=f"doc-{tenant}", project_id=project))
                await session.flush()
        yield session
    await state.engine.dispose()


def _shapes():
    doc = _Doc.__table__
    return {
        "join target": select(_Project.name).join(_Doc).where(_Doc.name == "doc-b"),
        "orm exists": select(_Project.id).where(
            select(_Doc.id).where(_Doc.project_id == _Project.id, _Doc.name == "doc-b").exists()
        ),
        "in_ subquery": select(_Project.id).where(
            _Project.id.in_(select(_Doc.project_id).where(_Doc.name == "doc-b"))
        ),
        "scalar subquery": select(select(func.count(_Doc.id)).scalar_subquery()),
        "count select_from": select(func.count()).select_from(_Doc),
        "count of subquery": select(func.count()).select_from(select(_Doc).subquery()),
        "core table": select(doc.c.name),
        "bare core exists": select(_Project.id).where(
            exists().where(_Doc.project_id == _Project.id, _Doc.name == "doc-b")
        ),
    }


# What tenant "a" must see for each shape: never tenant b's doc or project.
_EXPECTED_FOR_A = {
    "join target": [],
    "orm exists": [],
    "in_ subquery": [],
    "scalar subquery": [(1,)],
    "count select_from": [(1,)],
    "count of subquery": [(1,)],
    "core table": [("doc-a",)],
    "bare core exists": [],
}


@pytest.mark.parametrize("shape", list(_EXPECTED_FOR_A))
async def test_bound_tenant_never_sees_other_tenants(db: AsyncSession, shape: str):
    with tenant_context("a"):
        rows = (await db.execute(_shapes()[shape])).all()
    assert [tuple(r) for r in rows] == _EXPECTED_FOR_A[shape]


@pytest.mark.parametrize("shape", ["core table", "count select_from", "bare core exists"])
async def test_strict_without_tenant_fails_closed(db: AsyncSession, shape: str):
    stmt = _shapes()[shape]
    if shape in ("core table", "bare core exists"):
        with pytest.raises(MissingTenantError):
            await db.execute(stmt)
    else:  # indirect reference: matches nothing rather than every tenant
        assert (await db.execute(stmt)).scalar_one() == 0


async def test_core_update_and_delete_are_scoped(db: AsyncSession):
    doc = _Doc.__table__
    with tenant_context("a"):
        await db.execute(update(doc).values(name="renamed"))
        await db.execute(delete(doc).where(doc.c.name == "doc-b"))
    with tenant_context("b"):
        assert (await db.execute(select(_Doc.name))).scalars().all() == ["doc-b"]


async def test_core_insert_is_stamped(db: AsyncSession):
    with tenant_context("a"):
        await db.execute(insert(_Doc.__table__).values(name="core"))
        names = (await db.execute(select(_Doc.name).order_by(_Doc.name))).scalars().all()
    assert names == ["core", "doc-a"]

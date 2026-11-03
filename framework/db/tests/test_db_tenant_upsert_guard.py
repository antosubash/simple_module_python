"""Conflict updates obey the same tenant boundary as UPDATE (#749)."""

import pytest
from simple_module_db import (
    MultiTenantMixin,
    TenantIsolationError,
    all_tenants,
    create_module_base,
    tenant_context,
)
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Field

Base = create_module_base("upsert_guard_regression")


class UpsertRow(Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "upsert_guard_regression_row"
    id: int = Field(primary_key=True)
    name: str


@pytest.fixture
async def upsert_db():
    state = init_db("sqlite+aiosqlite:///:memory:")
    state.tenant_strict = True
    register_listeners(state)
    async with state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with state.session_factory() as db:
            with all_tenants():
                db.add_all(
                    [
                        UpsertRow(id=1, name="private", tenant_id="victim"),
                        UpsertRow(id=2, name="own", tenant_id="attacker"),
                    ]
                )
                await db.commit()
            with tenant_context("attacker"):
                yield db
    finally:
        await state.engine.dispose()


def statement(core, pk=1, **changes):
    target = UpsertRow.__table__ if core else UpsertRow
    return (
        insert(target)
        .values(id=pk, name="new", tenant_id="attacker")
        .on_conflict_do_update(index_elements=["id"], set_=changes)
    )


@pytest.mark.parametrize("core", [False, True])
async def test_upsert_cannot_update_foreign_row(upsert_db, core):
    await upsert_db.execute(statement(core, name="corrupted"))
    with all_tenants():
        assert await upsert_db.scalar(select(UpsertRow.name).where(UpsertRow.id == 1)) == "private"


@pytest.mark.parametrize("core", [False, True])
@pytest.mark.parametrize("column_key", [False, True])
async def test_upsert_cannot_assign_ownership(upsert_db, core, column_key):
    target = UpsertRow.__table__
    key = target.c.tenant_id if column_key else "tenant_id"
    stmt = (
        insert(target if core else UpsertRow)
        .values(id=1, name="new", tenant_id="attacker")
        .on_conflict_do_update(index_elements=["id"], set_={key: "attacker"})
    )
    with pytest.raises(TenantIsolationError):
        await upsert_db.execute(stmt)
    with all_tenants():
        assert (
            await upsert_db.scalar(select(UpsertRow.tenant_id).where(UpsertRow.id == 1)) == "victim"
        )


@pytest.mark.parametrize("core", [False, True])
async def test_same_tenant_upsert_and_original_where(upsert_db, core):
    await upsert_db.execute(statement(core, pk=2, name="updated"))
    assert await upsert_db.scalar(select(UpsertRow.name).where(UpsertRow.id == 2)) == "updated"
    target = UpsertRow.__table__ if core else UpsertRow
    stmt = (
        insert(target)
        .values(id=2, name="new", tenant_id="attacker")
        .on_conflict_do_update(
            index_elements=["id"],
            set_={"name": "wrong"},
            where=UpsertRow.__table__.c.name == "other",
        )
    )
    await upsert_db.execute(stmt)
    assert await upsert_db.scalar(select(UpsertRow.name).where(UpsertRow.id == 2)) == "updated"


@pytest.mark.parametrize("option", [False, True])
async def test_explicit_bypass_allows_upsert_ownership_move(upsert_db, option):
    stmt = statement(True, name="moved", tenant_id="attacker")
    if option:
        await upsert_db.execute(stmt.execution_options(all_tenants=True))
    else:
        with all_tenants():
            await upsert_db.execute(stmt)
    assert await upsert_db.scalar(select(UpsertRow.name).where(UpsertRow.id == 1)) == "moved"


def test_postgres_conflict_arm_is_scoped_without_mutating_the_callers_statement():
    from types import SimpleNamespace

    from simple_module_db.insert_guard import _guard_conflict_update
    from sqlalchemy.dialects.postgresql import dialect
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(UpsertRow).values(id=1, name="new", tenant_id="attacker")
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={"name": stmt.excluded.name},
        where=UpsertRow.__table__.c.name == "old",
    )
    state = SimpleNamespace(statement=stmt)
    _guard_conflict_update(state, "attacker")
    compiled = state.statement.compile(dialect=dialect())
    assert "WHERE upsert_guard_regression_row.name =" in str(compiled)
    assert "AND upsert_guard_regression_row.tenant_id =" in str(compiled)
    assert compiled.params["tenant_id_1"] == "attacker"
    assert "AND upsert_guard_regression_row.tenant_id" not in str(stmt.compile(dialect=dialect()))


async def test_do_nothing_remains_supported(upsert_db):
    stmt = insert(UpsertRow).values(id=1, name="new", tenant_id="attacker")
    await upsert_db.execute(stmt.on_conflict_do_nothing(index_elements=["id"]))
    with all_tenants():
        assert await upsert_db.scalar(select(UpsertRow.name).where(UpsertRow.id == 1)) == "private"


async def test_upsert_from_excluded_updates_own_row_only(upsert_db):
    base = insert(UpsertRow).values(id=2, name="refreshed", tenant_id="attacker")
    await upsert_db.execute(base.on_conflict_do_update(index_elements=["id"], set_=base.excluded))
    base = insert(UpsertRow).values(id=1, name="corrupted", tenant_id="attacker")
    await upsert_db.execute(base.on_conflict_do_update(index_elements=["id"], set_=base.excluded))
    with all_tenants():
        rows = dict((await upsert_db.execute(select(UpsertRow.id, UpsertRow.name))).all())
        owners = dict((await upsert_db.execute(select(UpsertRow.id, UpsertRow.tenant_id))).all())
    assert rows == {1: "private", 2: "refreshed"}
    assert owners == {1: "victim", 2: "attacker"}

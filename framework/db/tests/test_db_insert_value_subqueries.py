"""A subquery inside an INSERT's values reads like any SELECT: tenant and soft-delete scoped.

Covers ``.values()``, multi-row ``.values([...])`` and the ``set_`` / ``where``
of an ``ON CONFLICT DO UPDATE`` arm, Core and ORM subqueries alike, whatever
the insert's target is.
"""

import pytest
from _db_dml_scope_models import (
    ScopeDoc,
    ScopeProj,
    doc,
    docs,
    lax_db,
    projs,
    requires_sqlite,
    scope_db,
)
from simple_module_db.tenancy import TenantIsolationError, all_tenants, no_tenant, tenant_context
from sqlalchemy import String, cast, func, insert, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

__all__ = ["lax_db", "scope_db"]


def _name_of(doc_id, orm):
    if orm:
        return select(ScopeDoc.name).where(ScopeDoc.id == doc_id).scalar_subquery()
    return select(doc.c.name).where(doc.c.id == doc_id).scalar_subquery()


@pytest.mark.parametrize("orm", [False, True], ids=["core", "orm"])
async def test_values_subquery_into_tenant_table(scope_db, orm):
    with tenant_context("a"):
        await scope_db.execute(insert(ScopeDoc).values(id=10, note=_name_of(2, orm)))
        await scope_db.execute(insert(ScopeDoc).values(id=11, note=_name_of(1, orm)))
    rows = await docs(scope_db)
    assert (10, "a", "d", None) in rows
    assert (11, "a", "d", "a-doc") in rows


@pytest.mark.parametrize("orm", [False, True], ids=["core", "orm"])
async def test_values_subquery_into_untenanted_table(scope_db, orm):
    with tenant_context("a"):
        await scope_db.execute(insert(ScopeProj).values(id=10, note=_name_of(2, orm)))
        await scope_db.execute(insert(ScopeProj).values(id=11, note=_name_of(1, orm)))
    assert (await projs(scope_db))[2:] == [(10, None), (11, "a-doc")]


async def test_values_subquery_skips_trashed_rows(scope_db):
    with tenant_context("a"):
        await scope_db.execute(insert(ScopeProj).values(id=10, note=_name_of(4, orm=False)))
        await scope_db.execute(
            insert(ScopeProj)
            .values(id=11, note=_name_of(4, orm=True))
            .execution_options(include_deleted=True)
        )
    assert (await projs(scope_db))[2:] == [(10, None), (11, "a-trash")]


async def test_values_aggregate_subquery_counts_own_tenant(scope_db):
    count = select(func.count()).select_from(doc).scalar_subquery()
    with tenant_context("b"):
        await scope_db.execute(insert(ScopeProj).values(id=10, note=cast(count, String)))
    assert (await projs(scope_db))[2] == (10, "1")


@pytest.mark.parametrize("orm", [False, True], ids=["core", "orm"])
async def test_multi_values_subquery(scope_db, orm):
    rows = [{"id": 10, "note": _name_of(2, orm)}, {"id": 11, "note": _name_of(1, orm)}]
    with tenant_context("a"):
        await scope_db.execute(insert(ScopeProj).values(rows))
    assert (await projs(scope_db))[2:] == [(10, None), (11, "a-doc")]


@pytest.mark.parametrize("target", [ScopeProj, ScopeDoc], ids=["untenanted", "tenant"])
async def test_values_subquery_unbound_strict_fails_closed(scope_db, target):
    with no_tenant(), pytest.raises(TenantIsolationError):
        await scope_db.execute(insert(target).values(id=12, note=_name_of(2, orm=False)))


async def test_values_subquery_unbound_lax_reads_unfiltered(lax_db):
    await lax_db.execute(insert(ScopeProj).values(id=12, note=_name_of(2, orm=False)))
    assert (await projs(lax_db))[2] == (12, "b-secret")


async def test_values_subquery_all_tenants_reads_every_tenant(scope_db):
    with tenant_context("a"), all_tenants():
        await scope_db.execute(insert(ScopeProj).values(id=13, note=_name_of(2, orm=True)))
    assert (await projs(scope_db))[2] == (13, "b-secret")


@pytest.mark.parametrize("orm", [False, True], ids=["core", "orm"])
async def test_upsert_set_subquery(scope_db, orm):
    requires_sqlite(scope_db, "SQLite upsert syntax")
    stmt = sqlite_insert(ScopeDoc).values(id=1, name="x")
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_={"note": _name_of(2, orm)})
    with tenant_context("a"):
        await scope_db.execute(stmt)
    assert (1, "a", "a-doc", None) in await docs(scope_db)


async def test_upsert_where_subquery(scope_db):
    requires_sqlite(scope_db, "SQLite upsert syntax")
    probe = select(doc.c.id).where(doc.c.name == "b-secret").exists()
    stmt = sqlite_insert(ScopeDoc).values(id=1, name="x")
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_={"note": "hit"}, where=probe)
    with tenant_context("a"):
        await scope_db.execute(stmt)
    assert (1, "a", "a-doc", None) in await docs(scope_db)


async def test_plain_values_unchanged(scope_db):
    stmt = insert(ScopeProj).values(id=14, note="plain")
    with tenant_context("a"):
        await scope_db.execute(stmt)
    assert (await projs(scope_db))[2] == (14, "plain")

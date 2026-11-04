"""DML embedded as a CTE, ``INSERT OR REPLACE`` and the legacy ``Session.bulk_*`` APIs.

SQLite cannot run a data-modifying CTE, so those tests assert on the SQL the
engine is sent; on Postgres the statement runs and the rows are checked too.
"""

import pytest
from _db_dml_scope_models import ScopeDoc, ScopeProj, captured_sql, doc, docs, lax_db, scope_db
from simple_module_db.tenancy import TenantIsolationError, all_tenants, no_tenant, tenant_context
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import DBAPIError

__all__ = ["captured_sql", "lax_db", "scope_db"]


async def _run_cte(session, cte):
    try:
        await session.execute(select(cte.c.id))
    except DBAPIError:
        if session.bind.dialect.name != "sqlite":
            raise
        await session.rollback()


def _scoped_where(sql, keyword):
    """The DML inside the CTE has a ``tenant_id`` predicate before its RETURNING."""
    found = [q.split(keyword, 1)[1] for q in sql if keyword in q]
    return bool(found) and "tenant_id" in found[0].split("RETURNING")[0]


@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize("orm", [False, True], ids=["core", "orm"])
async def test_dml_cte_target_is_scoped(scope_db, captured_sql, operation, orm):
    target = ScopeDoc if orm else doc
    returning = ScopeDoc.id if orm else doc.c.id
    stmt = update(target).values(note="cte") if operation == "update" else delete(target)
    with tenant_context("a"):
        await _run_cte(scope_db, stmt.returning(returning).cte("w"))
    assert _scoped_where(captured_sql, f"{operation.upper()} "), captured_sql
    assert (2, "b", "b-secret", None) in await docs(scope_db)


async def test_dml_cte_unbound_strict_fails_closed(scope_db):
    cte = update(doc).values(note="cte").returning(doc.c.id).cte("w")
    with no_tenant(), pytest.raises(TenantIsolationError):
        await scope_db.execute(select(cte.c.id))


async def test_dml_cte_cannot_move_rows(scope_db):
    cte = update(doc).values(tenant_id="b").returning(doc.c.id).cte("w")
    with tenant_context("a"), pytest.raises(TenantIsolationError):
        await scope_db.execute(select(cte.c.id))


@pytest.mark.parametrize("orm", [False, True], ids=["core", "orm"])
async def test_insert_cte_is_refused(scope_db, orm):
    target = ScopeDoc if orm else doc
    returning = ScopeDoc.id if orm else doc.c.id
    cte = insert(target).values(id=30, tenant_id="b").returning(returning).cte("i")
    with tenant_context("a"), pytest.raises(TenantIsolationError):
        await scope_db.execute(select(cte.c.id))


async def test_dml_cte_all_tenants_is_left_alone(scope_db, captured_sql):
    cte = update(doc).values(note="cte").returning(doc.c.id).cte("w")
    with all_tenants():
        await _run_cte(scope_db, cte)
    assert not _scoped_where(captured_sql, "UPDATE ")


@pytest.mark.parametrize("prefix", ["OR REPLACE", "or replace"])
async def test_insert_or_replace_is_refused(scope_db, prefix):
    stmt = insert(doc).prefix_with(prefix).values(id=2, name="replacement")
    with tenant_context("a"), pytest.raises(TenantIsolationError):
        await scope_db.execute(stmt)
    assert (2, "b", "b-secret", None) in await docs(scope_db)


async def test_insert_or_ignore_is_allowed(scope_db):
    if scope_db.bind.dialect.name != "sqlite":
        pytest.skip("SQLite prefix")
    with tenant_context("a"):
        await scope_db.execute(insert(doc).prefix_with("OR IGNORE").values(id=2, name="x"))
    assert (2, "b", "b-secret", None) in await docs(scope_db)


async def test_insert_or_replace_all_tenants(scope_db):
    if scope_db.bind.dialect.name != "sqlite":
        pytest.skip("SQLite prefix")
    stmt = insert(doc).prefix_with("OR REPLACE").values(id=2, name="new", tenant_id="b")
    with all_tenants():
        await scope_db.execute(stmt)
    assert (2, "b", "new", None) in await docs(scope_db)


_LEGACY = {
    "bulk_update_mappings": lambda s: s.bulk_update_mappings(ScopeDoc, [{"id": 2, "note": "x"}]),
    "bulk_insert_mappings": lambda s: s.bulk_insert_mappings(
        ScopeDoc, [{"id": 20, "name": "x", "tenant_id": "b"}]
    ),
    "bulk_save_objects": lambda s: s.bulk_save_objects([ScopeDoc(id=20, name="x", tenant_id="b")]),
}


@pytest.mark.parametrize("method", sorted(_LEGACY))
async def test_legacy_bulk_api_refused_while_scoped(scope_db, method):
    with tenant_context("a"), pytest.raises(TenantIsolationError, match=method):
        await scope_db.run_sync(_LEGACY[method])
    with no_tenant(), pytest.raises(TenantIsolationError):
        await scope_db.run_sync(_LEGACY[method])
    assert [r[0] for r in await docs(scope_db)] == [1, 2, 3, 4]


@pytest.mark.parametrize("method", sorted(_LEGACY))
async def test_legacy_bulk_api_allowed_in_all_tenants(scope_db, method):
    with all_tenants():
        await scope_db.run_sync(_LEGACY[method])
        await scope_db.flush()


async def test_legacy_bulk_api_allowed_unbound_on_single_tenant_install(lax_db):
    await lax_db.run_sync(_LEGACY["bulk_update_mappings"])
    assert (2, "b", "b-secret", "x") in await docs(lax_db)


async def test_legacy_bulk_api_untenanted_model_unaffected(scope_db):
    with tenant_context("a"):
        await scope_db.run_sync(lambda s: s.bulk_insert_mappings(ScopeProj, [{"id": 9}]))

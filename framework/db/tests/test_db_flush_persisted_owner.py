"""A flushed UPDATE / DELETE must hit a row the bound tenant owns *in the database*.

The unit of work writes by primary key, so an object made persistent in
memory — ``make_transient_to_detached``, ``merge(load=False)``, a transient
copy given another row's key — must not carry an in-memory ``tenant_id`` onto
another tenant's row. Its owner is read from the table first; objects loaded
or inserted through the session are trusted and cost no extra read.
"""

import pytest
from _db_dml_scope_models import ScopeDoc, captured_sql, docs, scope_db
from simple_module_db._persisted_owner import _OWNER_KEY
from simple_module_db.flush_guard import guard_flush
from simple_module_db.tenancy import TenantIsolationError, all_tenants, tenant_context
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import make_transient, make_transient_to_detached
from sqlalchemy.orm.exc import StaleDataError

__all__ = ["captured_sql", "scope_db"]

B_SECRET = (2, "b", "b-secret", None)


def _in_memory(doc_id: int, tenant: str, name: str) -> ScopeDoc:
    obj = ScopeDoc(id=doc_id, name=name, tenant_id=tenant, is_deleted=False)
    make_transient_to_detached(obj)
    return obj


@pytest.mark.parametrize("op", ["update", "delete"])
async def test_detached_object_with_mismatched_owner_is_refused(scope_db, op):
    with tenant_context("a"):
        obj = _in_memory(2, "a", "b-secret")
        scope_db.add(obj)
        if op == "update":
            obj.name = "edited"
        else:
            await scope_db.delete(obj)
        with pytest.raises(TenantIsolationError, match="tenant 'b'"):
            await scope_db.flush()
    await scope_db.rollback()
    assert B_SECRET in await docs(scope_db)


async def test_merge_without_load_with_mismatched_owner_is_refused(scope_db):
    with tenant_context("a"):
        merged = await scope_db.merge(_in_memory(2, "a", "b-secret"), load=False)
        merged.name = "edited"
        with pytest.raises(TenantIsolationError):
            await scope_db.flush()
    await scope_db.rollback()
    assert B_SECRET in await docs(scope_db)


async def test_loaded_object_given_another_rows_key_is_refused(scope_db):
    with tenant_context("a"):
        own = await scope_db.get(ScopeDoc, 1)
        assert own is not None
        scope_db.expunge(own)
        make_transient(own)
        own.id = 2
        make_transient_to_detached(own)
        scope_db.add(own)
        own.name = "edited"
        with pytest.raises(TenantIsolationError):
            await scope_db.flush()
    await scope_db.rollback()
    assert B_SECRET in await docs(scope_db)


async def test_detached_object_of_the_bound_tenant_is_written(scope_db):
    with tenant_context("a"):
        own = _in_memory(1, "a", "a-doc")
        scope_db.add(own)
        own.note = "edited"
        await scope_db.flush()
    assert (1, "a", "a-doc", "edited") in await docs(scope_db)


async def test_missing_row_is_left_to_the_unit_of_work(scope_db):
    with tenant_context("a"):
        ghost = _in_memory(99, "a", "ghost")
        scope_db.add(ghost)
        ghost.note = "x"
        with pytest.raises(StaleDataError):
            await scope_db.flush()


async def test_all_tenants_block_is_not_checked(scope_db):
    with all_tenants():
        obj = _in_memory(2, "b", "b-secret")
        scope_db.add(obj)
        obj.note = "admin"
        await scope_db.flush()
    assert (2, "b", "b-secret", "admin") in await docs(scope_db)


async def test_loaded_and_inserted_objects_cost_no_extra_read(scope_db, captured_sql):
    with tenant_context("a"):
        loaded = (await scope_db.execute(select(ScopeDoc).where(ScopeDoc.id == 1))).scalar_one()
        fresh = ScopeDoc(id=5, name="new")
        scope_db.add(fresh)
        await scope_db.flush()
        captured_sql.clear()
        loaded.note = "edited"
        fresh.note = "edited"
        await scope_db.flush()
        await scope_db.delete(fresh)
        await scope_db.flush()
    assert captured_sql and all(sql.startswith("UPDATE") for sql in captured_sql)


async def test_detached_object_costs_one_read_then_none(scope_db, captured_sql):
    with tenant_context("a"):
        own = _in_memory(1, "a", "a-doc")
        scope_db.add(own)
        own.note = "first"
        captured_sql.clear()
        await scope_db.flush()
        own.note = "second"
        await scope_db.flush()
    assert [sql.split()[0] for sql in captured_sql] == ["SELECT", "UPDATE", "UPDATE"]


async def test_loaded_and_inserted_objects_are_not_marked(scope_db):
    """Normal loads and inserts do no per-row bookkeeping; only re-attached objects do."""
    with tenant_context("a"):
        loaded = (await scope_db.execute(select(ScopeDoc).where(ScopeDoc.id == 1))).scalar_one()
        fresh = ScopeDoc(id=6, name="new")
        scope_db.add(fresh)
        await scope_db.flush()
        reattached = _in_memory(3, "a", "x")
        scope_db.add(reattached)
    assert _OWNER_KEY not in sa_inspect(loaded).info
    assert _OWNER_KEY not in sa_inspect(fresh).info
    assert _OWNER_KEY in sa_inspect(reattached).info


async def test_missing_row_is_read_once(scope_db, captured_sql):
    with tenant_context("a"):
        ghost = _in_memory(99, "a", "ghost")
        scope_db.add(ghost)
        ghost.note = "x"
        captured_sql.clear()
        await scope_db.run_sync(guard_flush)
        await scope_db.run_sync(guard_flush)
    assert [sql.split()[0] for sql in captured_sql] == ["SELECT"]


async def test_soft_delete_of_a_loaded_object_costs_no_read_later(scope_db, captured_sql):
    with tenant_context("a"):
        own = await scope_db.get(ScopeDoc, 1)
        assert own is not None
        await scope_db.delete(own)
        await scope_db.flush()  # soft delete: expunged and re-added internally
        captured_sql.clear()
        own.note = "after"
        await scope_db.flush()
    assert [sql.split()[0] for sql in captured_sql] == ["UPDATE"]

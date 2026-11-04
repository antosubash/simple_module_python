"""UPDATE / DELETE shapes whose target or source the tenant filter has to resolve.

* ORM bulk UPDATE by primary key (``execute(update(M), [{"id": ...}])``);
* ``update().ordered_values()`` assigning ``tenant_id``;
* a DML on an aliased Core table (``delete(M.__table__.alias("v"))``);
* a table read only through an UPDATE's ``SET`` (``UPDATE ... FROM``).
"""

import pytest
from _db_dml_scope_models import ScopeDoc, ScopeOther, doc, docs, other, scope_db
from simple_module_db.tenancy import TenantIsolationError, all_tenants, no_tenant, tenant_context
from sqlalchemy import delete, select, update

__all__ = ["scope_db"]

# ``UPDATE ... FROM`` with no join condition is the shape under test.
_cartesian = pytest.mark.filterwarnings("ignore:UPDATE statement has a cartesian product")


async def test_bulk_pk_update_leaves_other_tenant_rows(scope_db):
    with tenant_context("a"):
        await scope_db.execute(update(ScopeDoc), [{"id": 2, "note": "x"}, {"id": 1, "note": "y"}])
    rows = await docs(scope_db)
    assert (2, "b", "b-secret", None) in rows
    assert (1, "a", "a-doc", "y") in rows


async def test_bulk_pk_update_synchronizes_own_tenant_objects(scope_db):
    with tenant_context("a"):
        own = await scope_db.get(ScopeDoc, 1)
        await scope_db.execute(update(ScopeDoc), [{"id": 1, "note": "synced"}])
        assert own.note == "synced"


@pytest.mark.parametrize("sync", [False, "evaluate"])
async def test_bulk_pk_update_explicit_synchronize(scope_db, sync):
    stmt = update(ScopeDoc).execution_options(synchronize_session=sync)
    with tenant_context("a"):
        await scope_db.execute(stmt, [{"id": 2, "note": "x"}, {"id": 1, "note": "y"}])
    rows = await docs(scope_db)
    assert (2, "b", "b-secret", None) in rows and (1, "a", "a-doc", "y") in rows


async def test_bulk_pk_update_reaches_trashed_rows_of_own_tenant(scope_db):
    with tenant_context("a"):
        await scope_db.execute(update(ScopeDoc), [{"id": 4, "note": "restored"}])
    assert (4, "a", "a-trash", "restored") in await docs(scope_db)


async def test_bulk_pk_update_unbound_strict_fails_closed(scope_db):
    with no_tenant(), pytest.raises(TenantIsolationError):
        await scope_db.execute(update(ScopeDoc), [{"id": 2, "note": "x"}])


async def test_bulk_pk_update_all_tenants(scope_db):
    with all_tenants():
        await scope_db.execute(update(ScopeDoc), [{"id": 2, "note": "x"}])
    assert (2, "b", "b-secret", "x") in await docs(scope_db)


@pytest.mark.parametrize("orm", [False, True], ids=["core", "orm"])
async def test_ordered_values_cannot_move_rows(scope_db, orm):
    column = ScopeDoc.tenant_id if orm else doc.c.tenant_id
    target = ScopeDoc if orm else doc
    stmt = update(target).ordered_values((column, "b"))
    with tenant_context("a"), pytest.raises(TenantIsolationError):
        await scope_db.execute(stmt.execution_options(synchronize_session=False))
    assert (1, "a", "a-doc", None) in await docs(scope_db)


async def test_ordered_values_without_tenant_is_scoped(scope_db):
    with tenant_context("a"):
        await scope_db.execute(update(doc).ordered_values((doc.c.note, "z")))
    rows = await docs(scope_db)
    assert {r[0] for r in rows if r[3] == "z"} == {1, 4}


@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_aliased_core_target_is_scoped(scope_db, operation):
    view = doc.alias("v")
    stmt = update(view).values(note="hit") if operation == "update" else delete(view)
    with tenant_context("a"):
        result = await scope_db.execute(stmt)
    assert result.rowcount == 2  # docs 1 and 4: trashed rows are writable
    assert (2, "b", "b-secret", None) in await docs(scope_db)


async def test_aliased_core_target_unbound_strict_fails_closed(scope_db):
    with no_tenant(), pytest.raises(TenantIsolationError):
        await scope_db.execute(delete(doc.alias("v")))


async def test_aliased_core_target_cannot_move_rows(scope_db):
    view = doc.alias("v")
    with tenant_context("a"), pytest.raises(TenantIsolationError):
        await scope_db.execute(update(view).values(tenant_id="b"))


@_cartesian
@pytest.mark.parametrize("orm", [False, True], ids=["core", "orm"])
async def test_update_from_set_source_is_scoped(scope_db, orm):
    source = ScopeOther.name if orm else other.c.name
    stmt = update(doc).where(doc.c.id == 1).values(note=source)
    with tenant_context("a"):
        await scope_db.execute(stmt)
    assert (1, "a", "a-doc", None) in await docs(scope_db)


@_cartesian
async def test_update_from_set_source_own_tenant(scope_db):
    with tenant_context("b"):
        await scope_db.execute(update(doc).where(doc.c.id == 2).values(note=other.c.name))
    assert (2, "b", "b-secret", "b-other") in await docs(scope_db)


async def test_update_from_set_source_unbound_strict_fails_closed(scope_db):
    stmt = update(ScopeOther).values(name=select(doc.c.name).where(doc.c.id == 2).scalar_subquery())
    with no_tenant(), pytest.raises(TenantIsolationError):
        await scope_db.execute(stmt)

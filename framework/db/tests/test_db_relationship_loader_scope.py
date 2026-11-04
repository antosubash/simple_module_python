"""Every relationship loader applies the same tenant / soft-delete scope (#816).

A plain relationship (``kids``) and one through a ``secondary`` link table
(``linked``) must load exactly the rows the scope lets the statement see,
whether the collection is loaded lazily, joined, by ``selectinload`` or by
``subqueryload``. The link table is a tenant-scoped, soft-deletable table:
its rows are filtered like the children's.
"""

import re

import pytest
from _db_read_scope_models import RsChild, RsParent, lax_read_db, link, read_db
from simple_module_db.tenancy import TenantIsolationError, all_tenants, no_tenant, tenant_context
from sqlalchemy import event, select
from sqlalchemy.orm import joinedload, selectinload, subqueryload

__all__ = ["lax_read_db", "read_db"]

LOADERS = {
    "lazy": None,
    "joinedload": joinedload,
    "selectinload": selectinload,
    "subqueryload": subqueryload,
}

# (context, execution options) -> expected (kids, linked) of parent 1
SCOPES = {
    "tenant": ("a", {}, [1, 2], [1]),
    "tenant-include-deleted": ("a", {"include_deleted": True}, [1, 2, 3], [1, 2]),
    "all-tenants": (None, {}, [1, 2, 4], [1, 2]),
}


async def _load(session, attr, loader, options):
    stmt = select(RsParent).execution_options(**options)
    if loader is not None:
        stmt = stmt.options(loader(getattr(RsParent, attr)))
    parent = (await session.execute(stmt)).unique().scalar_one()
    ids = await session.run_sync(lambda _sync: [c.id for c in getattr(parent, attr)])
    return sorted(set(ids))


@pytest.mark.parametrize("loader", list(LOADERS))
@pytest.mark.parametrize("attr", ["kids", "linked"])
@pytest.mark.parametrize("scope", list(SCOPES))
async def test_relationship_loader_matrix(read_db, loader, attr, scope):
    tenant, options, kids, linked = SCOPES[scope]
    if loader == "lazy" and options:
        pytest.skip("execution options belong to the statement, not to later lazy loads")
    expected = kids if attr == "kids" else linked
    with all_tenants() if tenant is None else tenant_context(tenant):
        assert await _load(read_db, attr, LOADERS[loader], options) == expected


@pytest.mark.parametrize("loader", ["joinedload", "selectinload", "subqueryload"])
async def test_secondary_loader_under_statement_all_tenants_option(read_db, loader):
    with tenant_context("a"):
        found = await _load(read_db, "linked", LOADERS[loader], {"all_tenants": True})
    assert found == [1, 2]


@pytest.mark.parametrize("loader", list(LOADERS))
async def test_single_tenant_install_sees_every_live_link(lax_read_db, loader):
    with no_tenant():
        assert await _load(lax_read_db, "linked", LOADERS[loader], {}) == [1, 2]


async def test_strict_without_tenant_refuses(read_db):
    with no_tenant(), pytest.raises(TenantIsolationError):
        await read_db.execute(select(RsParent).options(joinedload(RsParent.linked)))


async def test_join_through_secondary_relationship_is_scoped(read_db):
    stmt = select(RsParent.id, RsChild.id).join(RsParent.linked).order_by(RsChild.id)
    with tenant_context("a"):
        assert (await read_db.execute(stmt)).all() == [(1, 1)]


async def test_any_through_secondary_relationship_is_scoped(read_db):
    stmt = select(RsParent.id).where(RsParent.linked.any(RsChild.id == 2))
    with tenant_context("a"):
        assert (await read_db.execute(stmt)).all() == []
        found = await read_db.execute(stmt.execution_options(include_deleted=True))
        assert found.all() == [(1,)]


async def test_secondary_criteria_are_bound_per_execution(read_db):
    """One cached compiled form; the values come from each execution's scope."""
    sql: list[tuple[str, object]] = []
    engine = read_db.bind.sync_engine

    def capture(conn, cursor, statement, params, context, executemany):
        if link.name in statement:
            sql.append((statement, params))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        for tenant in ("a", "b"):
            with tenant_context(tenant):
                stmt = select(RsParent).options(selectinload(RsParent.linked))
                await read_db.execute(stmt.execution_options(all_tenants=True))
                read_db.expunge_all()
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(sql) == 2 and sql[0][0] == sql[1][0]
    assert [
        list(params).count(tenant) for (_sql, params), tenant in zip(sql, "ab", strict=True)
    ] == [1, 1]


async def test_subqueryload_renders_its_parent_subquery_once(read_db):
    sql: list[str] = []
    engine = read_db.bind.sync_engine

    def capture(conn, cursor, statement, params, context, executemany):
        sql.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with tenant_context("a"):
            await read_db.execute(select(RsParent).options(subqueryload(RsParent.kids)))
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    loader_sql = sql[-1]
    assert len(re.findall(r"\) AS anon_1\b", loader_sql)) == 1, loader_sql

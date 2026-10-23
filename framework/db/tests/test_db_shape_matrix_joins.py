"""Join predicates must filter nullable rows without losing their anchors (#597)."""

import pytest
from _db_shape_matrix import anchor, matrix_session, row, visible_ids
from simple_module_db._core_joins import scope_joins
from simple_module_db.query_filter import strict_configured
from simple_module_db.tenancy import TenantIsolationError, no_tenant, tenant_context
from sqlalchemy import select

__all__ = ["matrix_session"]


@pytest.mark.parametrize("outer", [False, True], ids=["join", "outerjoin"])
@pytest.mark.parametrize("setup", [False, True], ids=["explicit", "setup"])
@pytest.mark.parametrize("tenant", ["A", "B", None])
@pytest.mark.parametrize("include_deleted", [False, True])
async def test_join_matrix(matrix_session, outer, setup, tenant, include_deleted):
    on = row.c.id == anchor.c.id
    stmt = select(anchor.c.id, row.c.id)
    if setup:
        stmt = stmt.select_from(anchor).join(row, on, isouter=outer)
    else:
        stmt = stmt.select_from(anchor.join(row, on, isouter=outer))
    stmt = stmt.execution_options(include_deleted=include_deleted)
    with no_tenant() if tenant is None else tenant_context(tenant):
        if tenant is None and strict_configured(matrix_session.sync_session):
            with pytest.raises(TenantIsolationError):
                await matrix_session.execute(stmt)
        else:
            visible = visible_ids(tenant, include_deleted)
            expected = (
                [(i, i if i in visible else None) for i in range(1, 6)]
                if outer
                else [(i, i) for i in visible]
            )
            assert sorted((await matrix_session.execute(stmt)).all()) == expected


@pytest.mark.parametrize("outer", [False, True])
def test_scope_joins_places_nullable_predicate_in_on(outer):
    stmt = select(anchor.c.id, row.c.id).select_from(
        anchor.join(row, anchor.c.id == row.c.id, isouter=outer)
    )
    scoped = scope_joins(
        stmt, lambda table: [table.c.is_deleted.is_(False)] if table is row else []
    )
    assert scoped.covered == [row]
    assert bool(scoped.where) is (not outer)
    rewritten = stmt._generate()
    rewritten._from_obj = scoped.from_obj
    rewritten = rewritten.where(*scoped.where)
    sql = str(rewritten)
    before_where, _, where = sql.partition("WHERE")
    assert ("is_deleted" in before_where) is outer
    assert ("is_deleted" in where) is (not outer)

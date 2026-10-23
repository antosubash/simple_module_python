"""Select/walk matrix, using the same fixture on SQLite and Postgres (#597)."""

import pytest
from _db_shape_matrix import MatrixRow, anchor, matrix_session, row, visible_ids
from simple_module_db._core_walk import references_plain
from simple_module_db.query_filter import strict_configured
from simple_module_db.tenancy import TenantIsolationError, no_tenant, tenant_context
from sqlalchemy import delete, exists, select, union, update

__all__ = ["matrix_session"]


def statement(shape):
    if shape == "orm":
        return select(MatrixRow.id)
    if shape == "core":
        return select(row.c.id)
    if shape == "select_from":
        return select(anchor.c.id).select_from(anchor, row).where(anchor.c.id == row.c.id)
    if shape == "subquery":
        return select(select(row.c.id).subquery().c.id)
    if shape == "cte":
        return select(select(row.c.id).cte("scoped").c.id)
    if shape == "union":
        return union(select(row.c.id).where(row.c.id <= 2), select(row.c.id).where(row.c.id > 2))
    if shape == "exists":
        return select(anchor.c.id).where(exists().where(row.c.id == anchor.c.id))
    raise AssertionError(shape)


SHAPES = ["orm", "core", "select_from", "subquery", "cte", "union", "exists"]


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("tenant", ["A", "B", None], ids=["own", "other", "unbound"])
@pytest.mark.parametrize("include_deleted", [False, True])
async def test_select_matrix(matrix_session, shape, tenant, include_deleted):
    stmt = statement(shape).execution_options(include_deleted=include_deleted)
    with no_tenant() if tenant is None else tenant_context(tenant):
        if tenant is None and strict_configured(matrix_session.sync_session):
            with pytest.raises(TenantIsolationError):
                await matrix_session.execute(stmt)
        else:
            ids = (await matrix_session.execute(stmt)).scalars().all()
            assert sorted(ids) == visible_ids(tenant, include_deleted)


@pytest.mark.parametrize("shape", [*SHAPES, "update", "delete"])
def test_walk_detects_only_plain_scoped_references(shape):
    stmt = (
        update(row).values(name="changed")
        if shape == "update"
        else delete(row)
        if shape == "delete"
        else statement(shape)
    )
    assert references_plain(stmt, {row.name}) is (shape != "orm")
    assert references_plain(stmt, {"unrelated_table"}) is False

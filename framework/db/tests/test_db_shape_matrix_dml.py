"""Bulk DML scopes tenants but intentionally includes trashed targets (#597)."""

import pytest
from _db_shape_matrix import matrix_session, row, visible_ids
from simple_module_db.query_filter import strict_configured
from simple_module_db.tenancy import TenantIsolationError, no_tenant, tenant_context
from sqlalchemy import delete, select, update

__all__ = ["matrix_session"]


@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize("tenant", ["A", "B", None])
@pytest.mark.parametrize("include_deleted", [False, True])
async def test_dml_matrix(matrix_session, operation, tenant, include_deleted):
    stmt = update(row).values(name="changed") if operation == "update" else delete(row)
    stmt = stmt.execution_options(include_deleted=include_deleted)
    with no_tenant() if tenant is None else tenant_context(tenant):
        if tenant is None and strict_configured(matrix_session.sync_session):
            with pytest.raises(TenantIsolationError):
                await matrix_session.execute(stmt)
            affected = []
        else:
            result = await matrix_session.execute(stmt)
            affected = visible_ids(tenant, True)
            assert result.rowcount == len(affected)
    # Bypass both filters to prove *which* rows changed, including foreign/deleted rows.
    inspect = select(row.c.id, row.c.name).execution_options(all_tenants=True, include_deleted=True)
    actual = sorted((await matrix_session.execute(inspect)).all())
    expected = [
        (i, "changed" if i in affected else "original")
        for i in range(1, 5)
        if operation == "update" or i not in affected
    ]
    assert actual == expected

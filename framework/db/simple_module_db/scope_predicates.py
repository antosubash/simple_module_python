"""The predicates ``core_scope`` attaches, built from one statement's tenant scope.

``query_filter`` decides *whether* a statement is scoped (bound tenant, strict
mode, the ``all_tenants`` / ``include_deleted`` bypasses); this module turns
that decision into the callables ``core_scope`` applies to each Core
reference it finds: a table read (``subquery_predicates``) and a DML nested
inside another statement, such as an ``update(...).cte()`` under a SELECT
(``nested_dml_guard``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from simple_module_db import model_registry as registry
from simple_module_db._core_joins import _base_name
from simple_module_db.insert_guard import TENANT_COLUMN, statement_values
from simple_module_db.tenancy import TenantIsolationError, missing_tenant_error


def scoped_names(skip_soft_delete: bool, skip_tenant: bool) -> set[str]:
    names: set[str] = set()
    if not skip_soft_delete:
        names |= registry.soft_delete_table_names
    if not skip_tenant:
        names |= registry.tenant_table_names
    return names


def orm_covered(skip_soft_delete: bool, skip_tenant: bool, tenant_id: str | None) -> set[type]:
    """Classes whose every predicate the loader criteria put in a join's ``ON`` (#417).

    Strict mode without a tenant gives no tenant ``ON`` predicate worth the
    name, so a tenant class is covered only once a tenant is bound: a bare
    reference to it keeps refusing.
    """
    covered = set(registry.soft_delete_classes) if not skip_soft_delete else set()
    if skip_tenant or tenant_id is not None:
        covered |= registry.tenant_classes
    else:
        covered -= registry.tenant_classes
    return covered


def subquery_predicates(
    skip_soft_delete: bool, skip_tenant: bool, tenant_id: str | None, strict: bool
) -> Callable[[Any], list[Any]]:
    def predicates_for(from_obj: Any) -> list[Any]:
        # ``aliased(Model)`` / ``table.alias()`` is named after the alias, not
        # the table: resolve to the underlying table, filter on the alias.
        name = _base_name(from_obj)
        preds = []
        if not skip_soft_delete and name in registry.soft_delete_table_names:
            preds.append(from_obj.c.is_deleted.is_(False))
        if not skip_tenant and name in registry.tenant_table_names:
            if tenant_id is not None:
                preds.append(from_obj.c.tenant_id == tenant_id)
            elif strict:
                raise missing_tenant_error(name, "SELECT")
        return preds

    return predicates_for


def nested_dml_guard(
    skip_tenant: bool, tenant_id: str | None, strict: bool
) -> Callable[[Any], list[Any]]:
    """Rules for an INSERT / UPDATE / DELETE embedded in another statement (a CTE).

    Such a DML never reaches the filter as its own statement, so its target
    is handled here: an UPDATE / DELETE gets ``tenant_id = <bound>`` (and
    may not assign ``tenant_id``), and an INSERT on a tenant table is refused
    — its rows could be neither checked nor stamped. Strict mode with no
    tenant raises; ``all_tenants`` leaves them alone. Soft-delete never
    applies to a DML target.
    """

    def check(stmt: Any) -> list[Any]:
        name = _base_name(stmt.table)
        if skip_tenant or name not in registry.tenant_table_names:
            return []
        op = stmt.__visit_name__.upper()
        if tenant_id is None:
            if strict:
                raise missing_tenant_error(name, op)
            return []
        if op == "INSERT":
            raise TenantIsolationError(
                f"INSERT into tenant-scoped '{name}' inside another statement is not "
                "tenant-scoped; run it as a statement of its own"
            )
        if op == "UPDATE" and TENANT_COLUMN in statement_values(stmt):
            raise TenantIsolationError("Cannot change tenant_id of existing rows")
        return [stmt.table.c.tenant_id == tenant_id]

    return check


__all__ = ["nested_dml_guard", "orm_covered", "scoped_names", "subquery_predicates"]

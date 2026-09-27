"""``do_orm_execute`` filter: soft-delete and tenant scoping on every ORM query."""

from __future__ import annotations

from sqlalchemy.orm import ORMExecuteState, with_loader_criteria

from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.session import DatabaseState
from simple_module_db.tenancy import (
    ALL_TENANTS_OPTION,
    current_tenant_id,
    is_all_tenants,
    missing_tenant_error,
)

_db_state: DatabaseState | None = None


def configure_query_filter(db_state: DatabaseState) -> None:
    """Bind the filter to the app's ``DatabaseState`` (read for ``tenant_strict``)."""
    global _db_state
    _db_state = db_state


# Cache ``(is_soft_delete, is_multi_tenant)`` flags per mapper class so the
# ``do_orm_execute`` hot path skips redundant ``issubclass`` work on every query.
_mixin_flags_cache: dict[type, tuple[bool, bool]] = {}


def is_strict() -> bool:
    """Strict isolation is on for this DB and not waived by ``all_tenants()``."""
    return _db_state is not None and _db_state.tenant_strict and not is_all_tenants()


def filter_statements(execute_state: ORMExecuteState) -> None:
    """Attach per-mapper ``with_loader_criteria`` for soft-delete and tenant isolation.

    The criteria are attached per concrete mapper because SQLModel mixins
    expose Pydantic ``FieldInfo`` (not SQLAlchemy ``InstrumentedAttribute``)
    at the mixin-class level, which breaks the lambda form of
    ``with_loader_criteria`` that was used before the SQLModel migration.

    Soft-delete applies to SELECT only. Tenant scoping applies to ORM-enabled
    UPDATE and DELETE too — a bulk ``update(Model)`` would otherwise rewrite
    every tenant's rows. Without a tenant context, strict mode raises instead
    of leaving the statement unscoped.

    Soft-delete bypass: ``stmt.execution_options(include_deleted=True)``.
    Tenant bypass: ``stmt.execution_options(all_tenants=True)`` or ``all_tenants()``.
    """
    is_select = execute_state.is_select
    if not (is_select or execute_state.is_update or execute_state.is_delete):
        return

    options_in = execute_state.execution_options
    skip_soft_delete = not is_select or options_in.get("include_deleted", False)
    tenant_id = current_tenant_id.get()
    skip_tenant = options_in.get(ALL_TENANTS_OPTION, False) or is_all_tenants()
    strict = _db_state is not None and _db_state.tenant_strict
    if skip_soft_delete and (skip_tenant or (tenant_id is None and not strict)):
        return

    options = []
    for mapper in execute_state.all_mappers:
        cls = mapper.class_
        flags = _mixin_flags_cache.get(cls)
        if flags is None:
            flags = (issubclass(cls, SoftDeleteMixin), issubclass(cls, MultiTenantMixin))
            _mixin_flags_cache[cls] = flags
        is_soft_delete, is_multi_tenant = flags
        if is_soft_delete and not skip_soft_delete:
            options.append(
                with_loader_criteria(cls, cls.is_deleted.is_(False), include_aliases=True)
            )
        if not is_multi_tenant or skip_tenant:
            continue
        if tenant_id is not None:
            options.append(
                with_loader_criteria(cls, cls.tenant_id == tenant_id, include_aliases=True)
            )
        elif strict:
            op = "SELECT" if is_select else ("UPDATE" if execute_state.is_update else "DELETE")
            raise missing_tenant_error(cls.__name__, op)

    if options:
        execute_state.statement = execute_state.statement.options(*options)

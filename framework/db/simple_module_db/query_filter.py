"""``do_orm_execute`` filter: soft-delete and tenant scoping on every ORM statement.

Scope (#332, #506). Tenant and soft-delete criteria are attached for *every*
tenant-scoped / soft-deletable model, not only the entities a statement
names, so a table reached through a join target, an ORM ``exists()`` /
``in_()`` / scalar subquery or ``select(func.count()).select_from(Model)`` is
filtered too. Core references to ``Model.__table__`` (or an alias of it) get
explicit predicates at any depth — joins, subqueries, CTEs, compound
selects, the extra FROM of an UPDATE / DELETE (from its ``WHERE`` or its
``SET``), an INSERT's SELECT source and the subqueries in its values, and a
DML embedded as a CTE — see ``core_scope`` and ``insert_scope``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from simple_module_db import _secondary_scope  # noqa: F401  (registers the execution-scope listener)
from simple_module_db import model_registry as registry
from simple_module_db._bulk_pk_update import is_bulk_pk_update, scoped_bulk_pk_update
from simple_module_db._core_joins import _base_name, is_scoped_leaf
from simple_module_db._engine_policies import _engine_policy as _engine_policy  # re-exported
from simple_module_db._engine_policies import session_policy, set_policy
from simple_module_db._entity_selectables import refuse_aliased_core
from simple_module_db.core_scope import scope_core
from simple_module_db.insert_guard import TENANT_COLUMN as TENANT_COLUMN  # re-exported
from simple_module_db.insert_guard import assigned_tenant_ids, guard_insert
from simple_module_db.insert_scope import scope_insert
from simple_module_db.scope_predicates import (
    nested_dml_guard,
    orm_covered,
    scoped_names,
    subquery_predicates,
)
from simple_module_db.tenancy import (
    ALL_TENANTS_OPTION,
    DEFAULT_TENANT_ID,
    TenantIsolationError,
    current_tenant_id,
    is_all_tenants,
    missing_tenant_error,
)

# ``_engine_policy`` (imported above) is re-exported: the per-engine policy map lives in
# ``_engine_policies``; modules/background_tasks/tests/test_worker_tenancy.py reads it here.


class EngineTenancy:
    """Engine policy for an engine that has no ``DatabaseState``.

    ``audit_callback`` is the same sink a ``DatabaseState`` carries: writes made
    through this engine are audited only when it is set (#498);
    ``refuse_unaudited_dml`` is the strict bulk-audit switch (#557).
    """

    def __init__(
        self,
        *,
        tenant_strict: bool,
        default_tenant_id: str = DEFAULT_TENANT_ID,
        audit_callback: Callable[..., None] | None = None,
        refuse_unaudited_dml: bool | Callable[[], bool] = False,
    ) -> None:
        self.tenant_strict = tenant_strict
        self.default_tenant_id = default_tenant_id
        self.audit_callback = audit_callback
        self.refuse_unaudited_dml = refuse_unaudited_dml


def bind_engine_policy(engine: Engine, policy: Any) -> None:
    """Attach a policy (anything with ``tenant_strict``) to a sync engine.

    Engines derived from it (``engine.execution_options(...)``) and sessions
    bound to it per model (``binds={...}``) resolve to the same policy.
    """
    set_policy(engine, policy)


def engine_policy(session: Session) -> Any:
    """The policy bound to this session's engine, or ``None``."""
    return session_policy(session)


def strict_configured(session: Session) -> bool:
    policy = engine_policy(session)
    return bool(policy is not None and policy.tenant_strict)


def fallback_tenant_id(session: Session) -> str:
    """The tenant a non-strict write lands in when none is bound.

    The install's ``default_tenant`` when the host set one (published as
    ``DatabaseState.default_tenant_id``), else :data:`DEFAULT_TENANT_ID`.
    """
    policy = engine_policy(session)
    return getattr(policy, "default_tenant_id", None) or DEFAULT_TENANT_ID


def is_strict(session: Session) -> bool:
    """Strict isolation is on for this session's engine and not waived."""
    return strict_configured(session) and not is_all_tenants()


def filter_statements(execute_state: ORMExecuteState) -> Any:
    """Scope ORM statements by soft-delete and tenant.

    * SELECT: soft-delete + tenant loader criteria.
    * UPDATE / DELETE: tenant criteria, and an UPDATE may not assign
      ``tenant_id`` (the bulk sibling of the unit-of-work rule).
    * INSERT: explicit ``tenant_id`` values must match the bound tenant;
      missing ones are stamped with it (#357).

    Without a tenant, strict mode raises instead of leaving the statement
    unscoped. Bypass: ``execution_options(all_tenants=True)`` or
    ``all_tenants()``; soft-delete bypass: ``include_deleted=True``.
    """
    if execute_state.is_insert:
        session = execute_state.session
        _scope_insert_source(execute_state)
        return guard_insert(
            execute_state,
            strict=strict_configured(session),
            fallback=fallback_tenant_id(session),
        )
    is_select = execute_state.is_select
    if not (is_select or execute_state.is_update or execute_state.is_delete):
        return None

    options_in = execute_state.execution_options
    skip_soft_delete = not is_select or options_in.get("include_deleted", False)
    tenant_id = current_tenant_id.get()
    skip_tenant = options_in.get(ALL_TENANTS_OPTION, False) or is_all_tenants()
    strict = strict_configured(execute_state.session)
    if execute_state.is_update and not skip_tenant:
        # Before the early return: moving rows between tenants is refused
        # bound or not (#356), like the unit-of-work rule in flush_guard.
        _refuse_tenant_move(execute_state)
    if skip_soft_delete and (skip_tenant or (tenant_id is None and not strict)):
        return None

    options = []
    named: list[type] = []
    for mapper in execute_state.all_mappers:
        if registry.flags(mapper.class_)[1]:
            named.append(mapper.class_)
    execute_state.statement = scope_core(
        execute_state.statement,
        subquery_predicates(skip_soft_delete, skip_tenant, tenant_id, strict),
        scoped_names(skip_soft_delete, skip_tenant),
        orm_covered(skip_soft_delete, skip_tenant, tenant_id),
        nested_dml_guard(skip_tenant, tenant_id, strict),
        # A relationship loader's statement wraps one that was scoped when it ran.
        None if execute_state.is_relationship_load else refuse_aliased_core,
    )
    if not skip_soft_delete:
        options.extend(
            with_loader_criteria(c, c.is_deleted.is_(False), include_aliases=True)
            for c in registry.soft_delete_classes
        )
    if not skip_tenant:
        options.extend(_tenant_criteria(execute_state, named, tenant_id, strict))

    if options:
        execute_state.statement = execute_state.statement.options(*options)
    if named and tenant_id is not None and not skip_tenant and is_bulk_pk_update(execute_state):
        return scoped_bulk_pk_update(execute_state, named, tenant_id)
    return None


def _scope_insert_source(execute_state: ORMExecuteState) -> None:
    """What an INSERT reads — its SELECT source, its value subqueries — like any SELECT."""
    options = execute_state.execution_options
    skip_soft_delete = options.get("include_deleted", False)
    skip_tenant = options.get(ALL_TENANTS_OPTION, False) or is_all_tenants()
    names = scoped_names(skip_soft_delete, skip_tenant)
    if not names:
        return
    tenant_id = current_tenant_id.get()
    strict = strict_configured(execute_state.session)
    predicates_for = subquery_predicates(skip_soft_delete, skip_tenant, tenant_id, strict)
    nested = nested_dml_guard(skip_tenant, tenant_id, strict)
    execute_state.statement = scope_insert(
        execute_state.statement,
        lambda el: scope_core(
            el, predicates_for, names, nested=nested, aliased=refuse_aliased_core
        ),
    )


def _dml_target(execute_state: ORMExecuteState, names: set[str]) -> list[Any]:
    """The target of a Core UPDATE / DELETE on ``Model.__table__``, if scoped.

    Every other Core reference — in a SELECT, or joined in by an UPDATE /
    DELETE — is scoped by ``core_scope``.
    """
    if execute_state.is_select:
        return []
    target = getattr(execute_state.statement, "table", None)
    # ``delete(Model.__table__.alias("v"))`` is named after the alias.
    return [target] if target is not None and is_scoped_leaf(target, names) else []


def _tenant_criteria(
    execute_state: ORMExecuteState, named: list[type], tenant_id: str | None, strict: bool
) -> list[Any]:
    core = _dml_target(execute_state, registry.tenant_table_names)
    op = (
        "SELECT" if execute_state.is_select else ("UPDATE" if execute_state.is_update else "DELETE")
    )
    if tenant_id is None:
        if not strict:
            return []
        if named or core:
            raise missing_tenant_error(named[0].__name__ if named else str(_base_name(core[0])), op)
        # Indirect references (joins, subqueries) with no tenant bound match
        # nothing — tenant_id is NOT NULL — rather than every tenant.
        return [
            with_loader_criteria(c, c.tenant_id.is_(None), include_aliases=True)
            for c in registry.tenant_classes
        ]
    for table in core:
        execute_state.statement = execute_state.statement.where(table.c.tenant_id == tenant_id)
    return [
        with_loader_criteria(c, c.tenant_id == tenant_id, include_aliases=True)
        for c in registry.tenant_classes | set(named)
    ]


def _refuse_tenant_move(execute_state: ORMExecuteState) -> None:
    named = any(registry.flags(m.class_)[1] for m in execute_state.all_mappers)
    core = _dml_target(execute_state, registry.tenant_table_names)
    if (named or core) and assigned_tenant_ids(execute_state):
        raise TenantIsolationError("Cannot change tenant_id of existing rows")

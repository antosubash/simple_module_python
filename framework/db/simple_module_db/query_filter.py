"""``do_orm_execute`` filter: registered scopes on every ORM statement.

Tenant, soft-delete and module scopes use the same predicate pipeline below.

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
from sqlalchemy.sql import visitors

from simple_module_db import _secondary_scope  # noqa: F401  (registers the execution-scope listener)
from simple_module_db import model_registry as registry
from simple_module_db._builtin_scopes import tenant_scope
from simple_module_db._bulk_pk_update import is_bulk_pk_update, scoped_bulk_pk_update
from simple_module_db._core_joins import _base_name, _is_orm, is_scoped_leaf
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
from simple_module_db.scopes import ResolvedScope, resolve_scopes
from simple_module_db.tenancy import (
    DEFAULT_TENANT_ID,
    TenantIsolationError,
    is_all_tenants,
)

# ``_engine_policy`` (imported above) is re-exported: the per-engine policy map lives in
# ``_engine_policies``; the background_tasks worker tenancy test reads it here.


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
    """Apply all registered scopes to ORM entities and Core references."""
    session = execute_state.session
    is_insert = execute_state.is_insert
    is_write = execute_state.is_update or execute_state.is_delete
    if not (is_insert or is_write or execute_state.is_select):
        return None
    scopes = resolve_scopes(session, execute_state.execution_options, is_write=is_write)
    if execute_state.is_update and not tenant_scope.bypassed(execute_state.execution_options):
        _refuse_tenant_move(execute_state)
    if is_insert:
        _scope_insert_source(execute_state, scopes)
        from simple_module_db._scope_writes import guard_scope_insert

        guard_scope_insert(execute_state, scopes)
        return guard_insert(
            execute_state, strict=strict_configured(session), fallback=fallback_tenant_id(session)
        )
    if not any(r.active for r in scopes):
        return None
    names = scoped_names(scopes)
    if not names:
        return None
    # Loader options do nothing for wholly Core statements. Keep them for nested
    # ORM references too, even when the outer statement uses the Core compiler.
    statement: Any = execute_state.statement
    needs_loaders = execute_state.is_orm_statement or any(
        _is_orm(el) for el in visitors.iterate(statement)
    )
    execute_state.statement = scope_core(
        execute_state.statement,
        subquery_predicates(scopes),
        names,
        orm_covered(scopes) if needs_loaders else None,
        nested_dml_guard(scopes),
        None if execute_state.is_relationship_load else refuse_aliased_core,
    )
    options = []
    bulk_predicates = []
    named_classes = {m.class_ for m in execute_state.all_mappers}
    op = (
        "SELECT" if execute_state.is_select else ("UPDATE" if execute_state.is_update else "DELETE")
    )
    for resolved in scopes:
        scope = resolved.scope
        named = list(named_classes & scope._classes)
        core = _dml_target(execute_state, scope._table_names)
        explicit = (
            scope is not tenant_scope
            and any(
                _base_name(f) in scope._table_names
                for f in getattr(execute_state.statement, "_from_obj", ())
            )
            if resolved.required
            else False
        )
        if resolved.required and (named or core or explicit):
            raise scope.missing_error(
                named[0].__name__ if named else str(_base_name(core[0])) if core else scope.name, op
            )
        if not resolved.active:
            continue
        if execute_state.is_update and scope is not tenant_scope:
            from simple_module_db._scope_writes import refuse_scope_move

            if named or core:
                refuse_scope_move(execute_state, scope)
        for table in core:
            execute_state.statement = execute_state.statement.where(resolved.predicate(table.c))
        if needs_loaders:
            options.extend(
                with_loader_criteria(cls, resolved.predicate(cls), include_aliases=True)
                for cls in scope._classes
            )
        if execute_state.is_update:
            bulk_predicates.extend(resolved.predicate(cls) for cls in named)
    if options:
        execute_state.statement = execute_state.statement.options(*options)
    if bulk_predicates and is_bulk_pk_update(execute_state):
        return scoped_bulk_pk_update(execute_state, bulk_predicates)
    return None


def _scope_insert_source(execute_state: ORMExecuteState, scopes: list[ResolvedScope]) -> None:
    """An INSERT's source and value subqueries read through the same scope pipeline."""
    names = scoped_names(scopes)
    if not names:
        return
    predicates_for = subquery_predicates(scopes)
    nested = nested_dml_guard(scopes)
    execute_state.statement = scope_insert(
        execute_state.statement,
        lambda el: scope_core(
            el, predicates_for, names, nested=nested, aliased=refuse_aliased_core
        ),
    )


def _dml_target(execute_state: ORMExecuteState, names: set[str]) -> list[Any]:
    if execute_state.is_select:
        return []
    target = getattr(execute_state.statement, "table", None)
    return [target] if target is not None and is_scoped_leaf(target, names) else []


def _refuse_tenant_move(execute_state: ORMExecuteState) -> None:
    named = any(registry.flags(m.class_)[1] for m in execute_state.all_mappers)
    core = _dml_target(execute_state, registry.tenant_table_names)
    if (named or core) and assigned_tenant_ids(execute_state):
        raise TenantIsolationError("Cannot change tenant_id of existing rows")

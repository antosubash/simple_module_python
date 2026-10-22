"""Audit statement DML: ORM bulk and Core ``INSERT`` / ``UPDATE`` / ``DELETE`` (#557).

The unit-of-work capture in ``listeners`` sees only what a flush writes, so
``session.execute(update(Model)...)``, its ``delete()`` sibling and Core DML on
``Model.__table__`` used to leave no trace. :func:`audit_statement` is a
``do_orm_execute`` hook that closes that gap for every audited model:

* ``UPDATE`` / ``DELETE``: the primary keys the statement will touch are read
  first, with the same ``WHERE`` and the same tenant scope (soft-deleted rows
  included, as the write includes them). Up to :data:`BULK_AUDIT_ID_CAP` ids
  produce one record each (``bulk_updated`` / ``bulk_deleted`` /
  ``bulk_soft_deleted``, ``changes`` = the ``SET`` values); past the cap the
  statement is recorded once, ``entity_id`` ``"*"``, with its ``WHERE`` (bind
  placeholders, never literals) and row count.
* ``INSERT``: one summary record per statement.

Excluded columns (mixin bookkeeping, ``__audit_exclude_fields__``) are dropped
from ``changes``, and a statement that sets only excluded columns is not
recorded, exactly like a flush. ``execution_options(sm_audit=False)`` opts a
statement out; with ``refuse_unaudited_dml`` on the engine policy that raises
instead. ``text()`` writes are invisible here: record them with
:func:`record_bulk_audit`. Auditing never fails the write it describes.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import ORMExecuteState

from simple_module_db import model_registry as registry
from simple_module_db._bulk_audit_records import (  # noqa: F401  (re-exported)
    _ACTIVE_KEY,
    _SOFT_DELETE_FLAG,
    ACTION_BULK_DELETED,
    ACTION_BULK_INSERTED,
    ACTION_BULK_RESTORED,
    ACTION_BULK_SOFT_DELETED,
    ACTION_BULK_UPDATED,
    SUMMARY_ENTITY_ID,
    _bulk_by_pk_ids,
    _Ctx,
    _current_user,
    _deliver,
    _summary,
    _where_params,
    record_bulk_audit,
)
from simple_module_db.audit import _excluded_fields, format_pk
from simple_module_db.bulk_audit_targets import _is_set, _shown, _targets
from simple_module_db.query_filter import engine_policy
from simple_module_db.tenancy import ALL_TENANTS_OPTION

logger = logging.getLogger(__name__)

AUDIT_OPTION: Final = "sm_audit"
"""``execution_options(sm_audit=False)`` skips auditing for one statement."""

BULK_AUDIT_ID_CAP: Final = 500
"""Most rows a bulk statement records one by one; past it, one summary row."""


class UnauditedWriteError(RuntimeError):
    """An opted-out DML statement against an audited model, in strict mode."""


def _refuses_unaudited(policy: Any) -> bool:
    flag = getattr(policy, "refuse_unaudited_dml", False)
    return bool(flag() if callable(flag) else flag)


def _target_class(execute_state: ORMExecuteState) -> type | None:
    for mapper in execute_state.all_mappers:
        return mapper.class_
    table = getattr(execute_state.statement, "table", None)
    return registry.classes_by_table.get(table) if table is not None else None


def _plan(execute_state: ORMExecuteState, cls: type) -> _Ctx | None:
    """The record shape for this statement, or ``None`` when nothing is audited."""
    name = cls.__name__
    if execute_state.is_delete:
        return _Ctx(name, ACTION_BULK_DELETED, [])
    rows, many = _targets(execute_state, cls)
    default = ACTION_BULK_INSERTED if execute_state.is_insert else ACTION_BULK_UPDATED
    # The soft-delete flag picks a row's action; it is never a change, and
    # never bookkeeping that lets the statement go unrecorded.
    actions = [
        (ACTION_BULK_SOFT_DELETED if _is_set(row[_SOFT_DELETE_FLAG]) else ACTION_BULK_RESTORED)
        if execute_state.is_update and _SOFT_DELETE_FLAG in row
        else default
        for row in rows
    ]
    pk = {col.key for col in sa_inspect(cls).primary_key}
    # An executemany UPDATE names rows by primary key; anywhere else a written
    # key is a change and is never treated as bookkeeping.
    skip = _excluded_fields(cls) | pk if many and execute_state.is_update else _excluded_fields(cls)
    if execute_state.is_update:
        skip = skip | {_SOFT_DELETE_FLAG}  # it picked the action above
    written = list(dict.fromkeys(k for row in rows for k in row))
    kept = [k for k in written if k not in skip]
    # Only excluded columns: bookkeeping, like a flush. Never for an INSERT —
    # new rows are always recorded, at least as the summary.
    if execute_state.is_update and written and not kept and all(a == default for a in actions):
        return None
    if many:
        changes = [{"field": k} for k in kept]
    else:
        changes = [{"field": k, "new": _shown(rows[0][k])} for k in kept]
    ctx = _Ctx(name, actions[0] if actions else default, changes)
    ctx.row_actions = actions or [default]
    return ctx


def _prefetch_ids(execute_state: ORMExecuteState, cls: type, cap: int) -> list[str]:
    """Primary keys of the rows the statement will touch, at most ``cap + 1``."""
    stmt = execute_state.statement
    if execute_state.all_mappers:
        cols = [getattr(cls, col.key) for col in sa_inspect(cls).primary_key]
    else:
        cols = list(stmt.table.primary_key.columns)
    query = select(*cols).limit(cap + 1)
    if stmt.whereclause is not None:
        query = query.where(stmt.whereclause)
    options = {"include_deleted": True}
    if execute_state.execution_options.get(ALL_TENANTS_OPTION):
        options[ALL_TENANTS_OPTION] = True
    rows = execute_state.session.execute(
        query.execution_options(**options), _where_params(stmt, execute_state.parameters)
    ).all()
    return [format_pk(tuple(row)) for row in rows]


def _plans_a_record(execute_state: ORMExecuteState, cls: type) -> bool:
    """Whether the statement would be audited; a planning failure never refuses the write."""
    try:
        return _plan(execute_state, cls) is not None
    except Exception:
        logger.exception("Could not plan a bulk audit record for %s", cls.__name__)
        return False


def audit_statement(execute_state: ORMExecuteState) -> Any:
    """``do_orm_execute`` hook: audit statement DML on an audited model."""
    if not (execute_state.is_insert or execute_state.is_update or execute_state.is_delete):
        return None
    session = execute_state.session
    if session.info.get(_ACTIVE_KEY):
        return None
    cls = _target_class(execute_state)
    if cls is None or getattr(cls, "__audit_exclude__", False) is True:
        return None
    policy = engine_policy(session)
    if execute_state.execution_options.get(AUDIT_OPTION, True) is False:
        if _refuses_unaudited(policy) and _plans_a_record(execute_state, cls):
            raise UnauditedWriteError(
                f"Unaudited {AUDIT_OPTION}=False write to audited model {cls.__name__}"
            )
        return None
    callback = getattr(policy, "audit_callback", None)
    if callback is None:
        return None
    try:
        ctx = _plan(execute_state, cls)
    except Exception:
        logger.exception("Could not plan a bulk audit record for %s", cls.__name__)
        return None
    if ctx is None:
        return None
    params = execute_state.parameters
    ids = _bulk_by_pk_ids(execute_state, cls)
    by_row = ids is not None and len(ids) == len(ctx.row_actions)
    if ids is None and not (execute_state.is_insert or isinstance(params, list)):
        try:
            ids = _prefetch_ids(execute_state, cls, BULK_AUDIT_ID_CAP)
        except Exception:
            # Fail open: the write goes ahead, recorded as a summary row.
            logger.exception("Could not read the rows a bulk write touches on %s", cls.__name__)
            ids = None
    stmt = execute_state.statement
    result = execute_state.invoke_statement()
    if ids is not None and len(ids) <= BULK_AUDIT_ID_CAP:
        acts = ctx.row_actions if by_row else [ctx.action] * len(ids)
        records = [ctx.record(i, action=a) for i, a in zip(ids, acts, strict=True)]
    else:
        rowcount = len(params) if isinstance(params, list) else getattr(result, "rowcount", None)
        distinct = dict.fromkeys(ctx.row_actions)
        records = [_summary(ctx, stmt, rowcount, a) for a in distinct]
    _deliver(session, callback, records)
    return result

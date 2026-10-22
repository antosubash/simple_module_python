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
from collections.abc import Iterable
from typing import Any, Final

from simple_module_core.correlation import correlation_id
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import ORMExecuteState, Session

from simple_module_db import model_registry as registry
from simple_module_db.audit import AuditRecord, _excluded_fields, _serialize
from simple_module_db.bulk_audit_targets import _is_set, _shown, _targets
from simple_module_db.query_filter import engine_policy
from simple_module_db.tenancy import ALL_TENANTS_OPTION

logger = logging.getLogger(__name__)

AUDIT_OPTION: Final = "sm_audit"
"""``execution_options(sm_audit=False)`` skips auditing for one statement."""

BULK_AUDIT_ID_CAP: Final = 500
"""Most rows a bulk statement records one by one; past it, one summary row."""

ACTION_BULK_INSERTED: Final = "bulk_inserted"
ACTION_BULK_UPDATED: Final = "bulk_updated"
ACTION_BULK_DELETED: Final = "bulk_deleted"
ACTION_BULK_SOFT_DELETED: Final = "bulk_soft_deleted"
ACTION_BULK_RESTORED: Final = "bulk_restored"
SUMMARY_ENTITY_ID: Final = "*"

_SOFT_DELETE_FLAG: Final = "is_deleted"
_ACTIVE_KEY: Final = "_sm_bulk_audit_active"


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


def _pk_str(values: tuple | list) -> str:
    return str(values[0]) if len(values) == 1 else str(tuple(values))


class _Ctx:
    """What one audited statement records, built before it runs."""

    def __init__(self, entity_type: str, action: str, changes: list[dict[str, Any]]) -> None:
        self.entity_type = entity_type
        self.action = action
        self.row_actions = [action]
        self.changes = changes
        self.user_id = _current_user()
        self.correlation_id = correlation_id.get("") or None

    def record(
        self,
        entity_id: str,
        changes: list[dict[str, Any]] | None = None,
        action: str | None = None,
    ) -> AuditRecord:
        return AuditRecord(
            entity_type=self.entity_type,
            entity_id=entity_id,
            action=action or self.action,
            changes=self.changes if changes is None else changes,
            user_id=self.user_id,
            correlation_id=self.correlation_id,
        )


def _current_user() -> str | None:
    from simple_module_db.listeners import current_user_id

    return current_user_id.get()


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
    skip = skip | {_SOFT_DELETE_FLAG}
    written = list(dict.fromkeys(k for row in rows for k in row))
    kept = [k for k in written if k not in skip]
    if written and not kept and all(a == default for a in actions):
        return None  # only excluded columns: bookkeeping, like a flush
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
    rows = execute_state.session.execute(query.execution_options(**options)).all()
    return [_pk_str(tuple(row)) for row in rows]


def _bulk_by_pk_ids(execute_state: ORMExecuteState, cls: type) -> list[str] | None:
    """``session.execute(update(Model), [{pk..., col...}, ...])``: ids from the rows."""
    params = execute_state.parameters
    if not (execute_state.is_update and isinstance(params, list) and params):
        return None
    pk = [col.key for col in sa_inspect(cls).primary_key]
    if not all(all(k in row for k in pk) for row in params):
        return None
    return [_pk_str([row[k] for k in pk]) for row in params]


def _summary(ctx: _Ctx, stmt: Any, rowcount: Any, action: str) -> AuditRecord:
    where = getattr(stmt, "whereclause", None)
    summary = [
        {"field": "where_sql", "new": str(where) if where is not None else None},
        {"field": "rowcount", "new": rowcount},
        {"field": "truncated", "new": True},
    ]
    return ctx.record(SUMMARY_ENTITY_ID, [*ctx.changes, *summary], action)


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
        if _refuses_unaudited(policy) and _plan(execute_state, cls) is not None:
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
        ids = _prefetch_ids(execute_state, cls, BULK_AUDIT_ID_CAP)
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


def _deliver(session: Session, callback: Any, records: list[AuditRecord]) -> None:
    if not records:
        return
    session.info[_ACTIVE_KEY] = True
    try:
        callback(session, records)
    except Exception:
        logger.exception("Audit sink failed for %d bulk record(s)", len(records))
    finally:
        session.info.pop(_ACTIVE_KEY, None)


def record_bulk_audit(
    session: Any,
    entity_type: type | str,
    action: str,
    ids: Iterable[object] | None,
    changes: dict[str, Any] | None = None,
) -> None:
    """Audit a write the listeners cannot see — a ``text("UPDATE ...")`` statement.

    One record per id (``ids=None`` records one row with ``entity_id`` ``"*"``),
    in the session's transaction: a rollback discards them with the write.
    ``changes`` maps column name to new value. A no-op on an unaudited engine;
    never raises because of the audit sink. Accepts an ``AsyncSession`` or its
    sync ``Session``.
    """
    sync = getattr(session, "sync_session", session)
    callback = getattr(engine_policy(sync), "audit_callback", None)
    if callback is None:
        return
    name = entity_type if isinstance(entity_type, str) else entity_type.__name__
    diff = [{"field": k, "new": _serialize(v)} for k, v in (changes or {}).items()]
    ctx = _Ctx(name, action, diff)
    keys = [SUMMARY_ENTITY_ID] if ids is None else [str(i) for i in ids]
    _deliver(sync, callback, [ctx.record(k) for k in keys])

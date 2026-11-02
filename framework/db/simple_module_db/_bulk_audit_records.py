"""Audit record building and delivery shared by the bulk-audit hook and its manual entry point."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Final

from simple_module_core.correlation import correlation_id
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql.elements import BindParameter
from sqlalchemy.sql.visitors import iterate

from simple_module_db.audit import AuditRecord, _serialize, format_pk
from simple_module_db.query_filter import engine_policy

logger = logging.getLogger("simple_module_db.bulk_audit")

ACTION_BULK_INSERTED: Final = "bulk_inserted"
ACTION_BULK_UPDATED: Final = "bulk_updated"
ACTION_BULK_DELETED: Final = "bulk_deleted"
ACTION_BULK_SOFT_DELETED: Final = "bulk_soft_deleted"
ACTION_BULK_RESTORED: Final = "bulk_restored"
SUMMARY_ENTITY_ID: Final = "*"

_SOFT_DELETE_FLAG: Final = "is_deleted"
_ACTIVE_KEY: Final = "_sm_bulk_audit_active"


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


def _where_params(stmt: Any, params: Any) -> dict[str, Any] | None:
    """The execute params the ``WHERE`` clause binds, so the prefetch can run it."""
    where = getattr(stmt, "whereclause", None)
    if where is None or not isinstance(params, dict):
        return None
    keys = {e.key for e in iterate(where) if isinstance(e, BindParameter)}
    return {k: v for k, v in params.items() if k in keys} or None


def _bulk_by_pk_ids(execute_state: ORMExecuteState, cls: type) -> list[str] | None:
    """``session.execute(update(Model), [{pk..., col...}, ...])``: ids from the rows."""
    params = execute_state.parameters
    if not (execute_state.is_update and isinstance(params, list) and params):
        return None
    pk = [col.key for col in sa_inspect(cls).primary_key]
    if not all(all(k in row for k in pk) for row in params):
        return None
    return [format_pk([row[k] for k in pk]) for row in params]


def _summary(ctx: _Ctx, stmt: Any, rowcount: Any, action: str) -> AuditRecord:
    where = getattr(stmt, "whereclause", None)
    summary = [
        {"field": "where_sql", "new": str(where) if where is not None else None},
        {"field": "rowcount", "new": rowcount},
        {"field": "truncated", "new": True},
    ]
    return ctx.record(SUMMARY_ENTITY_ID, [*ctx.changes, *summary], action)


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

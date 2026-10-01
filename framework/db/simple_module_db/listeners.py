"""SQLAlchemy event listeners for auto-populating entity fields."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from simple_module_db.flush_guard import guard_flush
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.query_filter import bind_engine_policy, filter_statements
from simple_module_db.session import DatabaseState
from simple_module_db.writes import (
    _HARD_DELETE_KEY,
    SESSION_HAS_WRITES_KEY,
    _is_purge,
    _mark_dml_written,
    _mark_session_written,
    hard_delete,
    mark_written,
)

# Re-exported: ``transaction`` and published modules import these from here.
__all__ = [
    "SESSION_HAS_WRITES_KEY",
    "TenantIsolationError",
    "current_tenant_id",
    "current_user_id",
    "hard_delete",
    "mark_written",
    "register_listeners",
]

# Re-exported: callers import these from here since before tenancy.py existed.
from simple_module_db.tenancy import TenantIsolationError, current_tenant_id

logger = logging.getLogger(__name__)
_db_logger = logging.getLogger("simple_module.db")

# Set by auth middleware on each request
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)

# Key on ``Session.info`` for pending audit snapshots produced in before_flush
# and consumed in after_flush_postexec (when DB-assigned PKs are populated).
_AUDIT_PENDING_KEY = "_audit_pending"

# DB audit event names
_EVENT_ENTITY_CREATED = "db.entity.created"
_EVENT_ENTITY_UPDATED = "db.entity.updated"
_EVENT_ENTITY_SOFT_DELETED = "db.entity.soft_deleted"
_EVENT_ENTITY_DELETED = "db.entity.deleted"

_db_state: DatabaseState | None = None

# DB operation strings used in log extra dicts
_OP_CREATE = "create"
_OP_UPDATE = "update"
_OP_SOFT_DELETE = "soft_delete"
_OP_DELETE = "delete"


def _entity_label(obj: object) -> str:
    """Return 'ClassName' for a mapped entity instance."""
    return type(obj).__name__


def _entity_pk(obj: object) -> object:
    """Return the primary key value(s) if available, else None."""
    try:
        inspector = sa_inspect(obj)
        if inspector is None:
            return None
        identity = inspector.identity
        if identity and len(identity) == 1:
            return identity[0]
        return identity
    except Exception:
        return None


def register_listeners(db_state: DatabaseState) -> None:
    """Register SQLAlchemy event listeners for audit, soft delete, versioning, and tenancy.

    Registers on the engine-scoped session events. Safe to call multiple times
    — subsequent calls are no-ops.
    """
    if db_state._listeners_registered:
        logger.debug("Listeners already registered, skipping")
        return

    global _db_state
    _db_state = db_state
    # Strict mode is read from db_state at query time, per engine.
    bind_engine_policy(db_state.engine.sync_engine, db_state)
    attach_session_listeners(db_state.sync_session_class)
    db_state._listeners_registered = True
    logger.info("Registered SQLAlchemy entity listeners")


def attach_session_listeners(session_class: type[Session]) -> None:
    """Attach the entity listeners to a session class; idempotent.

    For a process with no ``DatabaseState`` (the Celery worker's sync engine),
    call this and ``bind_engine_policy(engine, EngineTenancy(...))``.
    """
    for name, fn in (
        ("before_flush", _before_flush_listener),
        ("after_flush", _mark_session_written),
        ("after_flush_postexec", _after_flush_audit),
        ("do_orm_execute", _mark_dml_written),
        ("do_orm_execute", filter_statements),
    ):
        if not event.contains(session_class, name, fn):
            event.listen(session_class, name, fn)


def _before_flush_listener(
    session: Session,
    flush_context: object,
    instances: object,
) -> None:
    guard_flush(session)
    user_id = current_user_id.get()
    now = datetime.now(UTC)

    for obj in session.new:
        if isinstance(obj, AuditMixin):
            if obj.created_by is None:
                obj.created_by = user_id
            if obj.updated_by is None:
                obj.updated_by = user_id

        _db_logger.info(
            _EVENT_ENTITY_CREATED,
            extra={
                "operation": _OP_CREATE,
                "entity": _entity_label(obj),
                "user_id": user_id,
            },
        )

    for obj in session.dirty:
        if not session.is_modified(obj):
            continue

        if isinstance(obj, AuditMixin):
            obj.updated_at = now
            obj.updated_by = user_id

        if isinstance(obj, VersionedMixin):
            obj.version += 1

        _db_logger.info(
            _EVENT_ENTITY_UPDATED,
            extra={
                "operation": _OP_UPDATE,
                "entity": _entity_label(obj),
                "entity_id": _entity_pk(obj),
                "user_id": user_id,
            },
        )

    # Deleted objects — convert to soft delete if applicable
    hard_delete_ids = session.info.pop(_HARD_DELETE_KEY, frozenset())
    for obj in list(session.deleted):
        if isinstance(obj, SoftDeleteMixin) and not _is_purge(obj, hard_delete_ids):
            # Cancel the hard delete
            session.expunge(obj)
            # Merge back as modified with soft-delete fields set
            obj.is_deleted = True
            obj.deleted_at = now
            obj.deleted_by = user_id
            session.add(obj)

            _db_logger.info(
                _EVENT_ENTITY_SOFT_DELETED,
                extra={
                    "operation": _OP_SOFT_DELETE,
                    "entity": _entity_label(obj),
                    "entity_id": _entity_pk(obj),
                    "user_id": user_id,
                },
            )
        else:
            _db_logger.info(
                _EVENT_ENTITY_DELETED,
                extra={
                    "operation": _OP_DELETE,
                    "entity": _entity_label(obj),
                    "entity_id": _entity_pk(obj),
                    "user_id": user_id,
                },
            )

    # Audit phase 1: snapshot diffs while attribute history is still available.
    # entity_id resolution is deferred to after_flush_postexec because
    # DB-assigned integer PKs aren't populated until the INSERT executes.
    if _db_state is not None and _db_state.audit_callback is not None:
        from simple_module_db.audit import snapshot_changes

        correlation_id_val: str | None = None
        try:
            from simple_module_hosting.logging import correlation_id as _cid_var

            correlation_id_val = _cid_var.get("") or None
        except ImportError:
            pass

        pending = snapshot_changes(session, user_id, correlation_id_val)
        if pending:
            session.info[_AUDIT_PENDING_KEY] = pending


def _after_flush_audit(session: Session, flush_context: object) -> None:
    """Phase 2: finalize audit records now that DB-assigned PKs are populated.

    Called via ``after_flush_postexec`` — after INSERTs have executed and
    SQLAlchemy has refreshed PK columns on the live object. Records added
    here land in ``session.new`` for the *next* flush (triggered by commit's
    autoflush). The recursion guard relies on AuditEntry having
    ``__audit_exclude__ = True`` so its own flush produces no pending records.
    """
    if _db_state is None or _db_state.audit_callback is None:
        return
    pending = session.info.pop(_AUDIT_PENDING_KEY, None)
    if not pending:
        return
    from simple_module_db.audit import finalize_records

    records = finalize_records(pending)
    if records:
        _db_state.audit_callback(session, records)

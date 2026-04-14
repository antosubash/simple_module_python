"""SQLAlchemy event listeners for auto-populating entity fields."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy.orm import Session, ORMExecuteState, with_loader_criteria

from simple_module_db.mixins import AuditMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.session import DatabaseState

logger = logging.getLogger(__name__)
_db_logger = logging.getLogger("simple_module.db")

# Set by auth middleware on each request
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def _entity_label(obj: object) -> str:
    """Return 'ClassName' for a mapped entity instance."""
    return type(obj).__name__


def _entity_pk(obj: object) -> object:
    """Return the primary key value(s) if available, else None."""
    from sqlalchemy import inspect as sa_inspect

    try:
        identity = sa_inspect(obj).identity
        if identity and len(identity) == 1:
            return identity[0]
        return identity
    except Exception:
        return None


def register_listeners(db_state: DatabaseState) -> None:
    """Register SQLAlchemy event listeners for audit, soft delete, and versioning.

    Registers on the engine-scoped session events. Safe to call multiple times
    — subsequent calls are no-ops.
    """
    if db_state._listeners_registered:
        logger.debug("Listeners already registered, skipping")
        return

    event.listen(db_state.sync_session_class, "before_flush", _before_flush_listener)
    event.listen(db_state.sync_session_class, "do_orm_execute", _soft_delete_filter)
    db_state._listeners_registered = True
    logger.info("Registered SQLAlchemy entity listeners")


def _before_flush_listener(
    session: Session,
    flush_context: object,
    instances: object,
) -> None:
    user_id = current_user_id.get()
    now = datetime.now(UTC)

    for obj in session.new:
        if isinstance(obj, AuditMixin):
            if obj.created_by is None:
                obj.created_by = user_id
            if obj.updated_by is None:
                obj.updated_by = user_id

        _db_logger.info(
            "db.entity.created",
            extra={
                "operation": "create",
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
            "db.entity.updated",
            extra={
                "operation": "update",
                "entity": _entity_label(obj),
                "entity_id": _entity_pk(obj),
                "user_id": user_id,
            },
        )

    # Deleted objects — convert to soft delete if applicable
    for obj in list(session.deleted):
        if isinstance(obj, SoftDeleteMixin):
            # Cancel the hard delete
            session.expunge(obj)
            # Merge back as modified with soft-delete fields set
            obj.is_deleted = True
            obj.deleted_at = now
            obj.deleted_by = user_id
            session.add(obj)

            _db_logger.info(
                "db.entity.soft_deleted",
                extra={
                    "operation": "soft_delete",
                    "entity": _entity_label(obj),
                    "entity_id": _entity_pk(obj),
                    "user_id": user_id,
                },
            )
        else:
            _db_logger.info(
                "db.entity.deleted",
                extra={
                    "operation": "delete",
                    "entity": _entity_label(obj),
                    "entity_id": _entity_pk(obj),
                    "user_id": user_id,
                },
            )


def _soft_delete_filter(execute_state: ORMExecuteState) -> None:
    """Automatically exclude soft-deleted rows from SELECT queries.

    Adds ``WHERE is_deleted = FALSE`` for every entity in the query that
    inherits from :class:`SoftDeleteMixin`.

    To bypass the filter (e.g. admin views), use::

        session.execute(stmt.execution_options(include_deleted=True))
    """
    if (
        execute_state.is_select
        and not execute_state.execution_options.get("include_deleted", False)
    ):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                SoftDeleteMixin,
                lambda cls: cls.is_deleted.is_(False),
                include_aliases=True,
            )
        )

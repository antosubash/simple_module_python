"""SQLAlchemy event listeners for auto-populating entity fields."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy.orm import Session

from simple_module_db.mixins import AuditMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.session import DatabaseState

logger = logging.getLogger(__name__)

# Set by auth middleware on each request
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def register_listeners(db_state: DatabaseState) -> None:
    """Register SQLAlchemy event listeners for audit, soft delete, and versioning.

    Registers on the engine-scoped session events. Safe to call multiple times
    — subsequent calls are no-ops.
    """
    if db_state._listeners_registered:
        logger.debug("Listeners already registered, skipping")
        return

    event.listen(db_state.sync_session_class, "before_flush", _before_flush_listener)
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

    for obj in session.dirty:
        if not session.is_modified(obj):
            continue

        if isinstance(obj, AuditMixin):
            obj.updated_at = now
            obj.updated_by = user_id

        if isinstance(obj, VersionedMixin):
            obj.version += 1

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

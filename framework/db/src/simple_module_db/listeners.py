"""SQLAlchemy event listeners for auto-populating entity fields."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import UTC, datetime

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session, with_loader_criteria

from simple_module_db.mixins import AuditMixin, MultiTenantMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.session import DatabaseState

logger = logging.getLogger(__name__)

# Set by auth middleware on each request
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)

# Set by tenant middleware on each request
current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


class TenantIsolationError(Exception):
    """Raised when a multi-tenancy isolation constraint is violated."""


def register_listeners(db_state: DatabaseState) -> None:
    """Register SQLAlchemy event listeners for audit, soft delete, versioning, and tenancy.

    Registers on the engine-scoped session events. Safe to call multiple times
    — subsequent calls are no-ops.
    """
    if db_state._listeners_registered:
        logger.debug("Listeners already registered, skipping")
        return

    event.listen(db_state.sync_session_class, "before_flush", _before_flush_listener)
    event.listen(db_state.sync_session_class, "do_orm_execute", _add_tenant_filter)
    db_state._listeners_registered = True
    logger.info("Registered SQLAlchemy entity listeners")


def _before_flush_listener(
    session: Session,
    flush_context: object,
    instances: object,
) -> None:
    user_id = current_user_id.get()
    tenant_id = current_tenant_id.get()
    now = datetime.now(UTC)

    for obj in session.new:
        if isinstance(obj, AuditMixin):
            if obj.created_by is None:
                obj.created_by = user_id
            if obj.updated_by is None:
                obj.updated_by = user_id

        # Auto-populate tenant_id; reject cross-tenant creation
        if isinstance(obj, MultiTenantMixin):
            if obj.tenant_id is None and tenant_id is not None:
                obj.tenant_id = tenant_id
            elif tenant_id is not None and obj.tenant_id != tenant_id:
                raise TenantIsolationError(
                    f"Cannot create object for tenant '{obj.tenant_id}' "
                    f"in context of tenant '{tenant_id}'"
                )

    for obj in session.dirty:
        if not session.is_modified(obj):
            continue

        if isinstance(obj, AuditMixin):
            obj.updated_at = now
            obj.updated_by = user_id

        if isinstance(obj, VersionedMixin):
            obj.version += 1

        # Prevent tenant_id from being changed on existing objects
        if isinstance(obj, MultiTenantMixin) and tenant_id is not None:
            hist = sa_inspect(obj).attrs.tenant_id.history
            if hist.has_changes():
                raise TenantIsolationError("Cannot change tenant_id of an existing object")

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


def _add_tenant_filter(orm_execute_state: object) -> None:
    """Automatically filter SELECT queries on multi-tenant models by current tenant.

    Uses ``with_loader_criteria`` so the filter applies to ``session.execute()``,
    ``session.get()``, and relationship lazy-loading.
    """
    if not orm_execute_state.is_select:  # type: ignore[union-attr]
        return

    tenant_id = current_tenant_id.get()
    if tenant_id is None:
        return

    orm_execute_state.statement = orm_execute_state.statement.options(  # type: ignore[union-attr]
        with_loader_criteria(
            MultiTenantMixin,
            lambda cls: cls.tenant_id == tenant_id,
            include_aliases=True,
        )
    )

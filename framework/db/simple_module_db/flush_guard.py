"""Unit-of-work tenant rules, applied in ``before_flush``.

The query filter scopes what a statement *reads*; this guards what a flush
*writes*. It covers the paths that never reach ``do_orm_execute``: objects
added with ``session.add``, and objects that came out of the identity map —
``session.get`` answers from it without SQL, so a session reused across a
``tenant_context`` switch can hand back, and then write, another tenant's row.
An object the session did not load or insert (``make_transient_to_detached``,
``merge(load=False)``, any detached object passed to ``session.add()``) has its
owner read from the table first (``_persisted_owner``).
"""

from __future__ import annotations

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from simple_module_db._persisted_owner import is_known, persisted_owner
from simple_module_db.mixins import MultiTenantMixin
from simple_module_db.query_filter import fallback_tenant_id, is_strict, strict_configured
from simple_module_db.tenancy import (
    TenantIsolationError,
    current_tenant_id,
    is_all_tenants,
    missing_tenant_error,
)


def _owner(obj: MultiTenantMixin) -> str | None:
    """The tenant the row belongs to in the database (before this flush)."""
    hist = sa_inspect(obj).attrs.tenant_id.history
    if hist.deleted:
        return hist.deleted[0]
    return obj.tenant_id


def _stamp_unbound(session: Session) -> None:
    """Non-strict and unscoped (unbound, or an ``all_tenants()`` block).

    New rows go to the bound tenant if there is one — a bypass widens what a
    block may *read*, it does not move its writes elsewhere — else to the
    install's fallback (``default_tenant`` or ``DEFAULT_TENANT_ID``).
    """
    stamp = current_tenant_id.get() or fallback_tenant_id(session)
    for obj in session.new:
        if isinstance(obj, MultiTenantMixin) and obj.tenant_id is None:
            obj.tenant_id = stamp


def guard_flush(session: Session) -> None:
    if is_all_tenants():
        # A bypass block is never scoped; on a single-tenant install its new
        # rows still need a tenant to satisfy NOT NULL (strict: left to the DB).
        if not strict_configured(session):
            _stamp_unbound(session)
        return
    tenant_id = current_tenant_id.get()
    strict = is_strict(session)
    if tenant_id is None and not strict:
        _stamp_unbound(session)

    for obj in session.new:
        if not isinstance(obj, MultiTenantMixin):
            continue
        if tenant_id is None and strict:
            raise missing_tenant_error(type(obj).__name__, "INSERT")
        if obj.tenant_id is None:
            if tenant_id is not None:
                obj.tenant_id = tenant_id
        elif tenant_id is not None and obj.tenant_id != tenant_id:
            raise TenantIsolationError(
                f"Cannot create object for tenant '{obj.tenant_id}' "
                f"in context of tenant '{tenant_id}'"
            )

    for obj in list(session.dirty) + list(session.deleted):
        if not isinstance(obj, MultiTenantMixin):
            continue
        is_deleted = obj in session.deleted
        if not is_deleted and not session.is_modified(obj):
            continue
        # Moving a row between tenants is never a routine edit, bound or not
        # (#356); only a deliberate all_tenants() block may do it.
        if not is_deleted and sa_inspect(obj).attrs.tenant_id.history.has_changes():
            raise TenantIsolationError("Cannot change tenant_id of an existing object")
        owner = _owner(obj)
        op = "DELETE" if is_deleted else "UPDATE"
        if tenant_id is None:
            if strict:
                raise missing_tenant_error(type(obj).__name__, op)
            continue
        if owner != tenant_id:
            raise _foreign_owner_error(op, owner, tenant_id)
        _check_persisted_owner(session, obj, owner, tenant_id, op)


def _foreign_owner_error(op: str, owner: str | None, tenant_id: str) -> TenantIsolationError:
    return TenantIsolationError(
        f"Cannot {op} an object of tenant '{owner}' in context of tenant '{tenant_id}'"
    )


def _check_persisted_owner(
    session: Session, obj: MultiTenantMixin, owner: str | None, tenant_id: str, op: str
) -> None:
    """The unit of work writes by primary key: the row itself must be the bound tenant's.

    Only an object the session did not load or insert costs a read — one made
    persistent in memory, whose ``tenant_id`` proves nothing — and only once
    per identity.
    """
    if is_known(obj, owner):
        return
    found, persisted = persisted_owner(session, obj)
    if found and persisted != tenant_id:
        raise _foreign_owner_error(op, persisted, tenant_id)


__all__ = ["guard_flush"]

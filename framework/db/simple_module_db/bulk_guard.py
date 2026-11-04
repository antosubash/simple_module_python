"""Tenant rules for the legacy bulk APIs of ``Session``.

``bulk_save_objects``, ``bulk_insert_mappings`` and ``bulk_update_mappings``
write through the persistence layer directly: no ``before_flush``, no
``do_orm_execute``, so neither the flush guard nor the query filter sees
them. On a ``MultiTenantMixin`` model they are refused while tenant scoping
is in force — a tenant is bound, or strict mode is on — and allowed inside
``all_tenants()`` (a deliberate cross-tenant write) and on a non-strict
install with nothing bound, where every write is unscoped anyway.

The 2.0 forms are scoped and are what to use instead:
``session.execute(insert(Model), rows)`` and
``session.execute(update(Model), rows)``.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from simple_module_db.mixins import MultiTenantMixin
from simple_module_db.query_filter import strict_configured
from simple_module_db.tenancy import TenantIsolationError, current_tenant_id, is_all_tenants

_GUARDED_ATTR = "_sm_bulk_guarded"


def _mapped_class(mapper: Any) -> type:
    return sa_inspect(mapper).class_


def _check(session: Session, method: str, classes: Iterable[type]) -> None:
    if is_all_tenants():
        return
    if current_tenant_id.get() is None and not strict_configured(session):
        return
    for cls in classes:
        if issubclass(cls, MultiTenantMixin):
            raise TenantIsolationError(
                f"Session.{method}() on tenant-scoped '{cls.__name__}' is not tenant-scoped; "
                "use session.execute(insert(Model), rows) / session.execute(update(Model), "
                "rows), or all_tenants() for a deliberate cross-tenant write"
            )


def _wrap(
    original: Callable[..., Any], method: str, subject: str, classes_of: Callable[..., Any]
) -> Any:
    """Check ``subject`` (the first parameter, positional or by keyword) before the call."""

    @functools.wraps(original)
    def guarded(self: Session, *args: Any, **kwargs: Any) -> Any:
        if args:
            first, rest = args[0], args[1:]
            if method == "bulk_save_objects":
                first = list(first)  # may be a one-shot iterator
            _check(self, method, classes_of(first))
            return original(self, first, *rest, **kwargs)
        if subject in kwargs:
            if method == "bulk_save_objects":
                kwargs[subject] = list(kwargs[subject])
            _check(self, method, classes_of(kwargs[subject]))
        return original(self, **kwargs)

    return guarded


def install_bulk_guard(session_class: type[Session]) -> None:
    """Guard the legacy bulk methods of ``session_class``; idempotent."""
    if any(base.__dict__.get(_GUARDED_ATTR) for base in session_class.__mro__):
        return
    for method, subject, classes_of in (
        ("bulk_save_objects", "objects", lambda objects: {type(o) for o in objects}),
        ("bulk_insert_mappings", "mapper", lambda mapper: [_mapped_class(mapper)]),
        ("bulk_update_mappings", "mapper", lambda mapper: [_mapped_class(mapper)]),
    ):
        setattr(
            session_class,
            method,
            _wrap(getattr(session_class, method), method, subject, classes_of),
        )
    setattr(session_class, _GUARDED_ATTR, True)


__all__ = ["install_bulk_guard"]

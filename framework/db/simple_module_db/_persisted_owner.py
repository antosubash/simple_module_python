"""The tenant a flushed row belongs to *in the database*, not only in memory.

The unit of work updates and deletes by primary key alone, so the flush guard
compares the bound tenant with the object's ``tenant_id``. That value is
trustworthy when the session loaded the object from (or inserted it into) the
database — but an object can also become persistent without either:
``make_transient_to_detached()``, ``merge(load=False)``, a transient copy given
another row's primary key, or any detached object passed to ``session.add()``.
Its ``tenant_id`` is then whatever was set in memory.

Every such object enters the session through ``detached_to_persistent``, and
only those are marked (``mark_unverified``): loads and inserts cost nothing.
A marked object has its owner read from the table (``persisted_owner``) before
the flush may write it; the answer — a row's ``tenant_id``, or no row — is
remembered with the identity it was read for, so it costs one ``SELECT``, once.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from simple_module_db.insert_guard import TENANT_COLUMN
from simple_module_db.mixins import MultiTenantMixin

_OWNER_KEY = "sm_unverified_owner"
_MISSING = object()  # the row was not found: the unit of work reports it
_UNCHECKED = (None, None)  # ``state.key`` is never ``None`` for a persistent object


def mark_unverified(session: Session, obj: Any) -> None:
    """``detached_to_persistent``: the session did not load or insert ``obj``."""
    if isinstance(obj, MultiTenantMixin):
        sa_inspect(obj).info[_OWNER_KEY] = _UNCHECKED


def owner_mark(obj: Any) -> Any:
    """``obj``'s mark, for ``restore_owner_mark`` after an expunge and re-add."""
    return sa_inspect(obj).info.get(_OWNER_KEY)


def restore_owner_mark(obj: Any, mark: Any) -> None:
    info = sa_inspect(obj).info
    if mark is None:
        info.pop(_OWNER_KEY, None)
    else:
        info[_OWNER_KEY] = mark


def is_known(obj: Any, owner: str | None) -> bool:
    """``obj`` was loaded or inserted by a session, or its owner was read for this identity."""
    state = sa_inspect(obj)
    mark = state.info.get(_OWNER_KEY)
    if mark is None:
        return True
    key, persisted = mark
    return key is not None and key == state.key and (persisted is _MISSING or persisted == owner)


def persisted_owner(session: Session, obj: Any) -> tuple[bool, str | None]:
    """``(found, tenant_id)`` of ``obj``'s row, read with Core (never tenant-filtered)."""
    state = sa_inspect(obj)
    mapper = state.mapper
    if state.key is None:
        return False, None
    column = mapper.columns[TENANT_COLUMN]
    match = [col == value for col, value in zip(mapper.primary_key, state.key[1], strict=True)]
    stmt = select(column).select_from(mapper.persist_selectable).where(and_(*match))
    rows = session.connection(bind_arguments={"mapper": mapper}).execute(stmt).all()
    if not rows:
        state.info[_OWNER_KEY] = (state.key, _MISSING)
        return False, None
    owner = rows[0][0]
    state.info[_OWNER_KEY] = (state.key, owner)
    return True, owner


__all__ = [
    "is_known",
    "mark_unverified",
    "owner_mark",
    "persisted_owner",
    "restore_owner_mark",
]

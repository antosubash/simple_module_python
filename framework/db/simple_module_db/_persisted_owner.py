"""The tenant a flushed row belongs to *in the database*, not only in memory.

The unit of work updates and deletes by primary key alone, so the flush guard
compares the bound tenant with the object's ``tenant_id``. That value is
trustworthy when the object was loaded from (or inserted into) the database —
but an object can also become persistent without either:
``make_transient_to_detached()``, ``merge(load=False)``, or ``make_transient``
and a new primary key. Its ``tenant_id`` is then whatever was set in memory.

So the session records, per object, the identity and ``tenant_id`` it was
loaded or inserted with (``remember_owner``). An object whose current
identity and ``tenant_id`` do not match that record has its owner read from
the table (``persisted_owner``) before the flush may write it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from simple_module_db.mixins import MultiTenantMixin

_OWNER_KEY = "sm_loaded_owner"
_TENANT = "tenant_id"


def remember_owner(session: Session, obj: Any) -> None:
    """``loaded_as_persistent`` / ``pending_to_persistent``: note what the row holds."""
    if isinstance(obj, MultiTenantMixin):
        state = sa_inspect(obj)
        if _TENANT in state.dict and state.key is not None:
            state.info[_OWNER_KEY] = (state.key, state.dict[_TENANT])


def is_known(obj: Any, owner: str | None) -> bool:
    """``obj``'s identity and ``owner`` are the ones it was loaded or inserted with."""
    state = sa_inspect(obj)
    return state.info.get(_OWNER_KEY) == (state.key, owner)


def persisted_owner(session: Session, obj: Any) -> tuple[bool, str | None]:
    """``(found, tenant_id)`` of ``obj``'s row, read with Core (never tenant-filtered)."""
    state = sa_inspect(obj)
    mapper = state.mapper
    if state.key is None:
        return False, None
    column = mapper.columns[_TENANT]
    match = [col == value for col, value in zip(mapper.primary_key, state.key[1], strict=True)]
    stmt = select(column).select_from(mapper.persist_selectable).where(and_(*match))
    rows = session.connection(bind_arguments={"mapper": mapper}).execute(stmt).all()
    if not rows:
        return False, None
    owner = rows[0][0]
    state.info[_OWNER_KEY] = (state.key, owner)
    return True, owner


__all__ = ["is_known", "persisted_owner", "remember_owner"]

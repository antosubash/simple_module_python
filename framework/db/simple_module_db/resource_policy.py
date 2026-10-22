"""The stock :class:`~simple_module_core.resources.ResourcePolicy` (GH #526).

:class:`OwnedResourcePolicy` covers the common shape — a row has an owner,
maybe a visibility flag, maybe shares in another table — as one SQL predicate::

    owner_col == :user_id
    OR visibility_col == 'public'          -- view only
    OR EXISTS (share for this principal)   -- from the injected factory

plus an explicit bypass permission. Because it is a ``WHERE`` on the caller's
own statement, :func:`~simple_module_db.pagination.paginate` counts exactly the
rows it lists. Tenant and soft-delete filters still apply on top.

``share_exists`` is injected (the optional ``sharing`` module provides one), so
nothing here imports a plugin (SM009).
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from simple_module_core.resources import ACTION_VIEW, ResourcePolicy, ResourcePrincipal
from sqlalchemy import false, inspect, or_

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.elements import ColumnElement

PUBLIC_VISIBILITY = "public"

ShareExists = Callable[[ResourcePrincipal, str], "ColumnElement[bool] | None"]
"""``(principal, action) -> EXISTS(...)`` for shares granting *action*, or ``None``."""


def _coerce(column: Any, value: str) -> Any:
    """*value* (a string id) in the Python type *column* compares against."""
    try:
        python_type = column.type.python_type
    except (AttributeError, NotImplementedError):
        return value
    if python_type is uuid.UUID:
        return uuid.UUID(str(value))
    if python_type is int:
        return int(value)
    return value


class OwnedResourcePolicy:
    """Owner / public / shared access, with an explicit bypass permission.

    ``bypass_perm`` is keyword-required: pass the permission that sees every
    row (``"notes.manage"``; an admin's wildcard satisfies it), or ``None`` to
    say on purpose that nobody bypasses ownership.
    """

    def __init__(
        self,
        owner_col: Any,
        *,
        bypass_perm: str | None,
        visibility_col: Any = None,
        share_exists: ShareExists | None = None,
        public_value: str = PUBLIC_VISIBILITY,
    ) -> None:
        self.owner_col = owner_col
        self.visibility_col = visibility_col
        self.share_exists = share_exists
        self.bypass_perm = bypass_perm
        self.public_value = public_value

    def predicate(self, principal: ResourcePrincipal, action: str) -> ColumnElement[bool] | None:
        """The ``WHERE`` clause, or ``None`` when the principal bypasses it."""
        if principal.has(self.bypass_perm):
            return None
        clauses: list[Any] = []
        if principal.user_id is not None:
            # An id that cannot be an owner (wrong type) owns nothing.
            with contextlib.suppress(ValueError):
                clauses.append(self.owner_col == _coerce(self.owner_col, principal.user_id))
            if self.share_exists is not None:
                shared = self.share_exists(principal, action)
                if shared is not None:
                    clauses.append(shared)
        if self.visibility_col is not None and action == ACTION_VIEW:
            clauses.append(self.visibility_col == self.public_value)
        return or_(*clauses) if clauses else false()

    def _owns(self, owner: Any, principal: ResourcePrincipal) -> bool:
        """The same comparison :meth:`predicate` sends to SQL, in Python."""
        try:
            return owner == _coerce(self.owner_col, principal.user_id or "")
        except ValueError:
            return False

    def filter(self, principal: ResourcePrincipal, action: str, stmt: Any) -> Any:
        clause = self.predicate(principal, action)
        return stmt if clause is None else stmt.where(clause)

    def can(self, principal: ResourcePrincipal, action: str, obj: Any) -> bool:
        if principal.has(self.bypass_perm):
            return True
        owner = getattr(obj, self.owner_col.key, None)
        if principal.user_id is not None and owner is not None and self._owns(owner, principal):
            return True
        if self.visibility_col is not None and action == ACTION_VIEW:
            return getattr(obj, self.visibility_col.key, None) == self.public_value
        return False


def select_by_id(model: type) -> Callable[[str], Any]:
    """A ``StatementForId`` for a single-primary-key table model.

    Raises ``ValueError`` for an id that cannot be the key's type, which
    callers turn into "not found".
    """
    from sqlmodel import select

    (pk,) = inspect(model).primary_key

    def build(resource_id: str) -> Any:
        return select(model).where(pk == _coerce(pk, resource_id))

    return build


async def load_authorized(
    session: AsyncSession,
    policy: ResourcePolicy,
    principal: ResourcePrincipal,
    action: str,
    stmt: Any,
) -> tuple[Any | None, bool]:
    """``(row, allowed)``: the row *principal* can see, and whether *action* is allowed.

    ``(None, False)`` means invisible (answer 404); ``(row, False)`` means
    visible but not allowed (403). Loads through :meth:`filter` only — never by
    raw id — then asks :meth:`can` and, if it says no, :meth:`filter` again for
    *action* (a share role lives outside the row).
    """
    row = (await session.execute(policy.filter(principal, ACTION_VIEW, stmt))).scalars().first()
    if row is None:
        return None, False
    if action == ACTION_VIEW or policy.can(principal, action, row):
        return row, True
    allowed = (await session.execute(policy.filter(principal, action, stmt))).scalars().first()
    return row, allowed is not None


__all__ = [
    "PUBLIC_VISIBILITY",
    "OwnedResourcePolicy",
    "ShareExists",
    "load_authorized",
    "select_by_id",
]

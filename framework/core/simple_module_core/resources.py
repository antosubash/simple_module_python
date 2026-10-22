"""Resource-scoped access: who may see or act on *this* row (GH #526).

Permissions are global ``<module>.<verb>`` strings; they say a principal may
edit *documents*, not *this* document. A :class:`ResourcePolicy` answers the
object-level question once per resource type, in two shapes that must agree:

* :meth:`ResourcePolicy.filter` narrows a ``SELECT`` to the rows *principal*
  may *action* — the authority. List endpoints and their counts run it, so a
  row a principal may not see never leaves the database.
* :meth:`ResourcePolicy.can` decides for one already-loaded row from the facts
  it carries (owner, visibility, a bypass permission). It may say ``False``
  where :meth:`filter` would admit the row (a share lives in another table);
  callers then fall back to :meth:`filter`, never the other way round.

The 404-vs-403 rule (``RequiresResource`` in ``simple_module_hosting``): a row
the principal may not *view* does not exist for them (404); a row they may
view but not *action* is a 403.

Modules declare their types in ``register_resource_types`` so cross-cutting
code (the optional ``sharing`` module) can find a type's policy and load a row
by its string id. ``simple_module_core`` stays SQLAlchemy-free: statements are
typed ``Any``; the stock policy lives in ``simple_module_db.resource_policy``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from simple_module_core.permissions import grants

ACTION_VIEW = "view"
"""Seeing the row at all; what decides 404 versus 403."""

ACTION_EDIT = "edit"
ACTION_DELETE = "delete"
ACTION_SHARE = "share"
"""Granting someone else access; the ``sharing`` module checks it on the granter."""

_TYPE_NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


@dataclass(frozen=True)
class ResourcePrincipal:
    """Who is asking: a user id (``None`` for anonymous) and what they hold.

    ``permissions`` is the request's resolved set (roles, grant sources, token
    scope cap) — the same set ``RequiresPermission`` reads, so a bypass
    permission is honoured or refused exactly as the door would.
    """

    user_id: str | None
    permissions: frozenset[str] = frozenset()

    def has(self, permission: str | None) -> bool:
        """Whether this principal holds *permission* (wildcard included).

        ``None`` or empty means "no permission configured" and answers ``False``
        — unlike :func:`grants`, a missing bypass must never grant everything.
        """
        return bool(permission) and grants(self.permissions, permission or "")


@runtime_checkable
class ResourcePolicy(Protocol):
    """Object-level access for one resource type. See the module docstring."""

    def filter(self, principal: ResourcePrincipal, action: str, stmt: Any) -> Any:
        """*stmt* narrowed to the rows *principal* may *action*."""
        ...

    def can(self, principal: ResourcePrincipal, action: str, obj: Any) -> bool:
        """Whether *principal* may *action* the loaded *obj* (fast path only)."""
        ...


StatementForId = Callable[[str], Any]
"""``(resource_id) -> SELECT`` of that one row, or raise ``ValueError`` for a malformed id."""


@dataclass(frozen=True)
class ResourceType:
    """A resource type a module exposes to cross-cutting access code.

    ``name`` is dotted and owned by the module (``"notes.note"``). ``select_by_id``
    builds the unfiltered ``SELECT`` for one row from its string id; callers
    always pass it through ``policy.filter`` before executing it.
    """

    name: str
    policy: ResourcePolicy
    select_by_id: StatementForId
    #: Actions a share may grant on this type, beyond :data:`ACTION_VIEW`.
    shareable_actions: tuple[str, ...] = field(default=(ACTION_VIEW, ACTION_EDIT))


class ResourceTypeError(ValueError):
    """A malformed or duplicate resource type declaration (raised at boot)."""


class ResourceTypeRegistry:
    """Resource types declared through ``register_resource_types``.

    Populated once at boot and read through ``app.state.sm.resource_types``.
    """

    def __init__(self) -> None:
        self._types: dict[str, ResourceType] = {}

    def register(self, resource_type: ResourceType) -> None:
        name = resource_type.name
        if not _TYPE_NAME.match(name):
            raise ResourceTypeError(f"Resource type name {name!r} must look like 'module.thing'")
        if name in self._types:
            raise ResourceTypeError(f"Resource type {name!r} is registered twice")
        self._types[name] = resource_type

    def get(self, name: str) -> ResourceType | None:
        return self._types.get(name)

    def all(self) -> list[ResourceType]:
        return sorted(self._types.values(), key=lambda t: t.name)

    def __contains__(self, name: object) -> bool:
        return name in self._types


__all__ = [
    "ACTION_DELETE",
    "ACTION_EDIT",
    "ACTION_SHARE",
    "ACTION_VIEW",
    "ResourcePolicy",
    "ResourcePrincipal",
    "ResourceType",
    "ResourceTypeError",
    "ResourceTypeRegistry",
    "StatementForId",
]

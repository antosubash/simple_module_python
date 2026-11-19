"""Read roles without depending on an auth provider's tables (#953).

Names are authorization keys. ``id`` optionally preserves a provider's local
record identity; it never participates in permission resolution. ``None`` user
roles means unknown, while an empty tuple means known to hold no roles.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from simple_module_core.tenancy import is_tenant_role

ROLE_DIRECTORY_STATE_ATTR = "role_directory"


@dataclass(frozen=True)
class DirectoryRole:
    name: str
    label: str
    description: str | None = None
    id: UUID | None = None


@runtime_checkable
class RoleDirectory(Protocol):
    #: Whether the provider supports local role definition and assignment.
    #: Permission mappings remain editable independently of this capability.
    editable: bool

    async def list_roles(self, db: Any) -> list[DirectoryRole]: ...

    async def user_roles(self, db: Any, user_id: str) -> tuple[str, ...] | None: ...


class NullRoleDirectory:
    """No registered provider: no known roles and no local role management."""

    editable = False

    async def list_roles(self, db: Any) -> list[DirectoryRole]:
        return []

    async def user_roles(self, db: Any, user_id: str) -> tuple[str, ...] | None:
        return None


class MappedRoleDirectory(NullRoleDirectory):
    """Application roles from live IdP mappings; account roles require claims."""

    def __init__(self, mapping: Callable[[], Mapping[str, str]]) -> None:
        self._mapping = mapping

    async def list_roles(self, db: Any) -> list[DirectoryRole]:
        # Match authentication: tenant roles come from memberships, never claims.
        names = {name for name in self._mapping().values() if not is_tenant_role(name)}
        return [DirectoryRole(name=name, label=name) for name in sorted(names)]


_NULL_DIRECTORY = NullRoleDirectory()


def set_role_directory(app: Any, directory: RoleDirectory) -> None:
    """Install the active auth provider's directory in ``register_settings``."""
    setattr(app.state, ROLE_DIRECTORY_STATE_ATTR, directory)


def get_role_directory(app: Any) -> RoleDirectory:
    directory = getattr(app.state, ROLE_DIRECTORY_STATE_ATTR, None)
    return directory if directory is not None else _NULL_DIRECTORY

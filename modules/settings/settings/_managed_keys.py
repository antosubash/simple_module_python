"""Rows of a key set by upload are not deleted by a bare row delete.

A key declaring ``SettingDefinition.clear_via`` is a file the owner's upload
route stores and reaps. Deleting the row any other way leaves the stored file
behind, so :meth:`SettingService.delete` / ``delete_scoped`` refuse it with
:class:`ManagedKeyError` **for every scope** — the rule lives in the service so
a route (or a module calling the service directly) cannot forget it.

Two ways through, both deliberate:

* the owner passes ``as_owner=True`` after taking responsibility for the file
  (branding's clear routes reap it);
* a TENANT row whose tenant no longer exists has no live owner left to clear
  it, so a platform operator may delete it by hand. SYSTEM and USER rows get no
  such exception: a SYSTEM row always has a live owner (the platform's own
  upload route), and a USER row of a managed key is cleared through the owner
  too. The guard is only as wide as the registry the service was built with;
  a service built without one (``SettingService(db)``) guards nothing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from settings.constants import ERR_MANAGED_KEY_DELETE
from settings.contracts.registry import SettingsRegistry
from settings.contracts.schemas import SettingScope

TenantIsLive = Callable[[str], Awaitable[bool]]


class ManagedKeyError(Exception):
    """The key is cleared through ``clear_via``, not by deleting its row."""

    def __init__(self, key: str, clear_via: str) -> None:
        self.key = key
        self.clear_via = clear_via
        super().__init__(ERR_MANAGED_KEY_DELETE.format(clear_via=clear_via))


async def ensure_deletable(
    registry: SettingsRegistry | None,
    tenant_is_live: TenantIsLive | None,
    scope: str,
    scope_id: str,
    key: str,
) -> None:
    """Raise :class:`ManagedKeyError` unless the row may be deleted generically."""
    definition = registry.get(key) if registry is not None else None
    if definition is None or not definition.clear_via:
        return
    orphaned = (
        scope == SettingScope.TENANT.value
        and tenant_is_live is not None
        and not await tenant_is_live(scope_id)
    )
    if orphaned:
        return
    raise ManagedKeyError(key, definition.clear_via)

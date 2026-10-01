"""Registry of declared setting keys — lets modules advertise the keys they
read so admins can see every knob (and its default) in one place.

Usage from a consumer module's ``on_startup`` hook:

    def on_startup(self, app):
        app.state.settings.registry.add(
            SettingDefinition(
                key="orders.checkout.require_terms",
                default="true",
                description="Show the terms-and-conditions checkbox on checkout.",
            )
        )

The registry doesn't write anything to the database — it only records
intent. ``SettingsAccessor.get`` falls back to the registered default when
no row exists at any scope. ``get_bool`` / ``get_int`` / ``get_json`` cast
the stored string representation on the way out.

API mirrors the other framework registries (MenuRegistry / PermissionRegistry
/ FeatureFlagRegistry): ``add(definition)`` + ``all_definitions``. Unlike
FeatureFlagRegistry, duplicate keys raise — settings carry defaults and a
second registration almost always means two owners contended for the same key.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from settings.constants import ERR_KEY_ALREADY_EXISTS
from settings.contracts.schemas import SettingScope, SettingValueType

if TYPE_CHECKING:
    from starlette.requests import Request

TenantValueCheck = Callable[["Request", str, str], Awaitable[None]]
"""``async (request, tenant_id, value)`` run before a TENANT-scope write.

Raise ``ValueError`` to reject the value (422) or ``LookupError`` when it names
something the tenant does not have (404) — e.g. a file id owned by another
tenant. ``tenant_id`` is the scope being written, which on the platform routes
is not the caller's own active tenant."""


@dataclass(frozen=True, slots=True)
class SettingDefinition:
    """Declared metadata for a setting key.

    ``tenant_overridable`` opts the key into tenant self-service (#382): a
    tenant owner/admin may write it for their *own* active tenant through
    ``/api/settings/tenant/current/{key}``. Keys without it are writable at
    tenant scope only by platform operators (``settings.edit``). ``check``
    vets every TENANT-scope write of the key, from either surface.
    ``clear_via`` names the route that owns clearing the key (e.g. an upload
    route that also reaps the stored file): the generic DELETE routes answer
    422 pointing there while the tenant exists. A platform operator may still
    delete the row left behind by a tenant that no longer exists. A key whose
    system and tenant rows are cleared through different routes passes a
    ``{SettingScope: route}`` mapping; read it with :func:`clear_route`.
    """

    key: str
    default: str = ""
    description: str = ""
    scope: SettingScope = SettingScope.SYSTEM
    value_type: SettingValueType = SettingValueType.STRING
    tenant_overridable: bool = False
    check: TenantValueCheck | None = field(default=None, compare=False)
    clear_via: str | Mapping[SettingScope, str] = ""


def clear_route(definition: SettingDefinition, scope: SettingScope | str) -> str:
    """The route that clears ``definition`` at ``scope`` ("" if unmanaged).

    A scope the mapping does not name falls back to its first route, so the
    refusal still points somewhere rather than at nothing.
    """
    via = definition.clear_via
    if isinstance(via, str):
        return via
    if not via:
        return ""
    return via.get(SettingScope(scope)) or next(iter(via.values()))


@dataclass(slots=True)
class SettingsRegistry:
    """In-memory registry of declared setting keys. Populated at module boot
    so admins (and other modules) can discover every knob the app exposes.
    """

    _defs: dict[str, SettingDefinition] = field(default_factory=dict)

    def add(self, definition: SettingDefinition) -> None:
        if definition.key in self._defs:
            raise ValueError(f"{ERR_KEY_ALREADY_EXISTS}: {definition.key!r}")
        self._defs[definition.key] = definition

    def get(self, key: str) -> SettingDefinition | None:
        return self._defs.get(key)

    @property
    def all_definitions(self) -> list[SettingDefinition]:
        return list(self._defs.values())

    @property
    def tenant_overridable(self) -> list[SettingDefinition]:
        """Definitions a tenant may override for itself, sorted by key."""
        return sorted((d for d in self._defs.values() if d.tenant_overridable), key=lambda d: d.key)

    def __contains__(self, key: str) -> bool:
        return key in self._defs

"""Registry of declared setting keys — lets modules advertise the keys they
read so admins can see every knob (and its default) in one place.

Usage from a consumer module's ``on_startup`` hook:

    def on_startup(self, app):
        registry = app.state.settings.registry
        registry.register(
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
"""

from __future__ import annotations

from dataclasses import dataclass, field

from settings.constants import ERR_KEY_ALREADY_EXISTS
from settings.contracts.schemas import SettingScope, SettingValueType


@dataclass(frozen=True, slots=True)
class SettingDefinition:
    """Declared metadata for a setting key."""

    key: str
    default: str = ""
    description: str = ""
    scope: SettingScope = SettingScope.SYSTEM
    value_type: SettingValueType = SettingValueType.STRING


@dataclass(slots=True)
class SettingsRegistry:
    """In-memory registry of declared setting keys. Populated at module boot
    so admins (and other modules) can discover every knob the app exposes.
    """

    _defs: dict[str, SettingDefinition] = field(default_factory=dict)

    def register(self, definition: SettingDefinition) -> None:
        if definition.key in self._defs:
            raise ValueError(f"{ERR_KEY_ALREADY_EXISTS}: {definition.key!r}")
        self._defs[definition.key] = definition

    def get(self, key: str) -> SettingDefinition | None:
        return self._defs.get(key)

    def all(self) -> list[SettingDefinition]:
        return list(self._defs.values())

    def __contains__(self, key: str) -> bool:
        return key in self._defs

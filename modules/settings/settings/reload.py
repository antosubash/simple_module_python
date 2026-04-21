"""Apply a set of field changes to a module's settings and reload them.

Steps:
1. Look up the module's BaseSettings class from the registry.
2. Merge changes over current DB overrides + defaults to form the candidate.
3. Construct ``cls(**candidate)`` — pydantic validates.
4. On success, write each change to the store, reassign ``app.state.<package>.settings``,
   and publish ``SettingsReloaded``.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from pydantic_settings import BaseSettings
from simple_module_core.events import EventBus

from settings.constants import MODULE_PACKAGE
from settings.contracts.events import SettingsReloaded
from settings.hydrate import hydrate_settings, value_type_for_field
from settings.store import SettingsStore


def _encode(value: Any, value_type: str) -> str:
    if value_type == "json":
        return json.dumps(value)
    return str(value)


async def apply_changes_and_reload(
    app: FastAPI,
    bus: EventBus,
    store: SettingsStore,
    *,
    package: str,
    changes: dict[str, Any],
) -> BaseSettings:
    """Validate, persist, hot-swap, and publish ``SettingsReloaded``."""
    registry = getattr(app.state, MODULE_PACKAGE).module_registry
    cls = registry.get(package)
    if cls is None:
        raise KeyError(f"Unknown settings package: {package!r}")

    unknown = set(changes) - set(cls.model_fields)
    if unknown:
        raise KeyError(f"Unknown field(s) for {package!r}: {sorted(unknown)}")

    current = await hydrate_settings(cls, store, package)
    merged = current.model_dump()
    merged.update(changes)
    validated = cls(**merged)

    for field_name, raw_value in changes.items():
        vtype = value_type_for_field(cls, field_name)
        encoded = _encode(raw_value, vtype)
        await store.set_override(package, field_name, encoded, vtype)

    services = getattr(app.state, package)
    services.settings = validated

    await bus.publish(SettingsReloaded(package=package, changed=tuple(sorted(changes))))
    return validated

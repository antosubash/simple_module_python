"""Apply field changes to a module's settings, validate, persist, hot-swap."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from pydantic_settings import BaseSettings
from simple_module_core.events import EventBus

from settings.constants import MODULE_PACKAGE
from settings.contracts.events import SettingsReloaded
from settings.hydrate import value_type_for_field
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

    services = getattr(app.state, package)
    current = services.settings
    diff = {k: v for k, v in changes.items() if getattr(current, k) != v}
    if not diff:
        return current

    merged = current.model_dump()
    merged.update(diff)
    validated = cls(**merged)

    for field_name, raw_value in diff.items():
        vtype = value_type_for_field(cls, field_name)
        await store.set_override(package, field_name, _encode(raw_value, vtype), vtype)

    services.settings = validated
    await bus.publish(SettingsReloaded(package=package, changed=tuple(sorted(diff))))
    return validated

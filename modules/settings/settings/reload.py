"""Apply field changes to a module's settings, validate, persist, hot-swap."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from pydantic_settings import BaseSettings
from simple_module_core.events import EventBus

from settings.constants import MODULE_PACKAGE
from settings.contracts.events import SettingsReloaded
from settings.hydrate import env_supplied_fields, value_type_for_field
from settings.store import SettingsStore


class EnvPinnedError(ValueError):
    """A change targets fields the environment sets, which always win (GH #486).

    Storing it anyway would hot-swap the value into this process only: every
    restart and every other worker would hydrate the env value instead.
    """

    def __init__(self, fields: list[str]) -> None:
        super().__init__(f"Set by the environment: {', '.join(fields)}")
        self.fields = fields


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

    pinned = sorted(set(changes) & env_supplied_fields(cls))
    if pinned:
        raise EnvPinnedError(pinned)

    services = getattr(app.state, package)
    current = services.settings
    # Compare against the *dumped* current value, not the attribute: a field
    # typed as a list of models (branding's ``footer_links``) holds model
    # instances, while ``changes`` carries the plain dicts a DTO dumps to. The
    # attribute comparison never matched those, so an unchanged list was
    # rewritten to the store on every save.
    merged = current.model_dump()
    diff = {k: v for k, v in changes.items() if merged.get(k) != v}
    if not diff:
        return current

    merged.update(diff)
    validated = cls(**merged)

    # A json field stores what validated, not what was sent: a field validator
    # may have turned the editor's text into the declared type (``json.loads``
    # on a dict), and encoding the raw input stored a JSON *string* that
    # hydration could not read back as that type (GH #487). Scalars keep the
    # submitted value — a serializer (``SecretStr`` dumps as asterisks) must
    # never decide what is written to the store.
    for field_name, raw_value in diff.items():
        vtype = value_type_for_field(cls, field_name)
        if vtype == "json":
            raw_value = validated.model_dump(mode="json", include={field_name}).get(
                field_name, raw_value
            )
        await store.set_override(package, field_name, _encode(raw_value, vtype), vtype)

    services.settings = validated
    await bus.publish(SettingsReloaded(package=package, changed=tuple(sorted(diff))))
    return validated

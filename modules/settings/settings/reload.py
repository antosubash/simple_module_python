"""Apply field changes to a module's settings, validate, persist, hot-swap."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from pydantic import SecretBytes, SecretStr, ValidationError
from pydantic_core import to_jsonable_python
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


def _unwrap_secrets(value: Any) -> Any:
    """``value`` with every ``SecretStr``/``SecretBytes`` replaced by its secret.

    The store needs the real credential: a JSON dump masks secrets as
    asterisks, also when they sit inside ``X | None`` or a container.
    """
    if isinstance(value, SecretStr | SecretBytes):
        return value.get_secret_value()
    if isinstance(value, dict):
        return {k: _unwrap_secrets(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_unwrap_secrets(v) for v in value]
    return value


def _relocate(exc: ValidationError, field_name: str) -> ValidationError:
    """Re-key a stored-value error (``loc=["value"]``) onto the field it was for.

    The write schema validates the encoded ``value`` column, which names no
    settings field, so the editor could not show it anywhere.
    """
    lines: list[Any] = [
        {
            "type": e["type"],
            "loc": (field_name, *e["loc"][1:]),
            "input": e.get("input"),
            "ctx": e.get("ctx", {}),
        }
        for e in exc.errors()
    ]
    return ValidationError.from_exception_data(exc.title, lines)


def _is_default(cls: type[BaseSettings], field_name: str, value: Any) -> bool:
    """Whether the validated ``value`` is what the field defaults to."""
    info = cls.model_fields[field_name]
    if info.is_required():
        return False
    default = info.get_default(call_default_factory=True)
    return to_jsonable_python(_unwrap_secrets(default)) == to_jsonable_python(
        _unwrap_secrets(value)
    )


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
    # Compare against the *dumped* current value, not the attribute: a field
    # typed as a list of models (branding's ``footer_links``) holds model
    # instances, while ``changes`` carries the plain dicts a DTO dumps to. The
    # attribute comparison never matched those, so an unchanged list was
    # rewritten to the store on every save.
    merged = current.model_dump()
    diff = {k: v for k, v in changes.items() if merged.get(k) != v}
    if not diff:
        return current

    # Only a field that would actually change is refused: a client that echoes
    # the whole GET payload back resubmits env-set fields at their live value.
    pinned = sorted(set(diff) & env_supplied_fields(cls))
    if pinned:
        raise EnvPinnedError(pinned)

    merged.update(diff)
    validated = cls(**merged)
    dumped_all = validated.model_dump()

    # A json field stores what validated, not what was sent: a field validator
    # may have turned the editor's text into the declared type (``json.loads``
    # on a dict), and encoding the raw input stored a JSON *string* that
    # hydration could not read back as that type (GH #487). Scalars keep the
    # submitted value. Either way a serializer (``SecretStr`` dumps as
    # asterisks) must never decide what is written to the store, so secrets
    # are unwrapped before the validated value is made JSON-able.
    for field_name, raw_value in diff.items():
        vtype = value_type_for_field(cls, field_name)
        if _is_default(cls, field_name, dumped_all.get(field_name, raw_value)):
            # Saving the default is clearing the override: a stored row would
            # keep the field labelled "overridden in DB" while holding exactly
            # what the code would have supplied anyway.
            await store.clear_override(package, field_name)
            continue
        if vtype == "json":
            dumped = validated.model_dump(include={field_name}).get(field_name, raw_value)
            raw_value = to_jsonable_python(_unwrap_secrets(dumped))
        try:
            await store.set_override(package, field_name, _encode(raw_value, vtype), vtype)
        except ValidationError as exc:
            raise _relocate(exc, field_name) from exc

    services.settings = validated
    await bus.publish(SettingsReloaded(package=package, changed=tuple(sorted(diff))))
    return validated

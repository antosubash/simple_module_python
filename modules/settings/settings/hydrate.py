"""Resolve a module's BaseSettings from DB overrides + pydantic defaults.

A field's declared Python type maps to one of the five ``value_type`` labels
understood by SettingsStore (``string | bool | int | float | json``). The
hydrator reads overrides, parses each according to its stored ``value_type``,
and constructs the BaseSettings — pydantic enforces field validators and any
``@model_validator`` hooks.
"""

from __future__ import annotations

import json
from typing import TypeVar, get_origin

from pydantic_settings import BaseSettings

from settings.store import SettingsStore

T = TypeVar("T", bound=BaseSettings)


def value_type_for_field(cls: type[BaseSettings], field_name: str) -> str:
    """Return the ``value_type`` label for a field based on its annotation.

    - ``bool`` → ``"bool"``
    - ``int`` → ``"int"``
    - ``float`` → ``"float"``
    - ``str`` and enums → ``"string"``
    - ``list``, ``dict``, and other container types → ``"json"``
    """
    info = cls.model_fields[field_name]
    ann = info.annotation
    origin = get_origin(ann)
    if origin is not None:
        return "json"
    if ann is bool:
        return "bool"
    if ann is int:
        return "int"
    if ann is float:
        return "float"
    return "string"


def _parse(raw: str, value_type: str):  # noqa: ANN202
    if value_type == "bool":
        return raw.lower() in ("1", "true", "yes", "on")
    if value_type == "int":
        return int(raw)
    if value_type == "float":
        return float(raw)
    if value_type == "json":
        return json.loads(raw)
    return raw


async def hydrate_settings(cls: type[T], store: SettingsStore, package: str) -> T:
    """Construct ``cls`` with DB overrides merged over pydantic defaults."""
    raw_overrides = await store.get_overrides(package)
    parsed: dict[str, object] = {}
    for field_name, (raw, vtype) in raw_overrides.items():
        if field_name not in cls.model_fields:
            continue
        parsed[field_name] = _parse(raw, vtype)
    return cls(**parsed)

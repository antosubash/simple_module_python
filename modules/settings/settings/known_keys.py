"""Suggestions for the free-form key field, with enough meta to resolve them.

The key field is free text, and a typo produces a row that looks saved and is
silently never read — the failure gives no feedback at all. Suggesting the
registered keys makes the common case unmissable without forbidding the
uncommon one: keys outside this list stay valid, since a module can read
settings the settings module cannot enumerate.

Each suggestion also carries what the New override screen's "Resolved value"
panel needs — the env fallback and the module default — so an admin can see
that the override they are about to write is the value the app already has.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder

from settings._module_settings import collect_module_settings

_DEFINITION_MODULE = "Registry"
"""Module label for keys declared through ``SettingsRegistry`` rather than a
pydantic settings class. They have no owning package to name — the registry
records intent, not a field on some module's settings object."""


def _from_field(package: str, module_name: str, field) -> dict[str, Any]:
    return {
        "key": f"{package}.{field.name}",
        "type": field.type,
        "description": field.description,
        "module": module_name,
        "env_var": field.env_var,
        # See ``ModuleSettingField.env_readable``: a bundled module's SM_* var
        # is a label, not a fallback, and the panel must say so.
        "env_readable": field.env_readable,
        "env_set": field.env_set,
        "env_value": field.env_value,
        "default": jsonable_encoder(field.default),
        "requires_restart": field.requires_restart,
        "is_secret": field.is_secret,
        "choices": field.choices,
    }


def _from_definition(definition) -> dict[str, Any]:
    return {
        "key": definition.key,
        "type": str(definition.value_type),
        "description": definition.description,
        "module": _DEFINITION_MODULE,
        "env_var": "",
        "env_readable": False,
        "env_set": False,
        "env_value": None,
        "default": definition.default,
        "requires_restart": False,
        "is_secret": False,
        "choices": None,
    }


def build(app: FastAPI) -> list[dict[str, Any]]:
    """Every ``<package>.<field>`` a module reads, plus every declared key.

    Module fields win over registry declarations of the same key: the pydantic
    field is the one the app actually reads, while a declaration only records
    intent and can go stale without anything failing.
    """
    suggestions: dict[str, dict[str, Any]] = {}
    for view in collect_module_settings(app):
        for field in view.fields:
            entry = _from_field(view.package, view.module_name, field)
            suggestions[entry["key"]] = entry

    registry = getattr(getattr(app.state, "settings", None), "registry", None)
    if registry is not None:
        for definition in registry.all_definitions:
            suggestions.setdefault(definition.key, _from_definition(definition))

    return [suggestions[key] for key in sorted(suggestions)]

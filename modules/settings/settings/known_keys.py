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
from settings._secrets import conceals_secret, mask


def _from_field(package: str, field) -> dict[str, Any]:
    return {
        "key": f"{package}.{field.name}",
        "type": field.type,
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
    """A registry declaration, masked on the same rule as a module field.

    ``_from_field`` receives a default that ``_module_settings`` has already
    masked; this builder reads the declaration directly, so it has to apply the
    rule itself. Hard-coding ``is_secret: False`` and passing ``default``
    straight through put the raw value into the New-override suggestion list,
    which renders it verbatim.
    """
    value_type = str(definition.value_type)
    default = jsonable_encoder(definition.default)
    secret = conceals_secret(definition.key, default, value_type)
    return {
        "key": definition.key,
        "type": value_type,
        "env_var": "",
        "env_readable": False,
        "env_set": False,
        "env_value": None,
        "default": mask(default) if secret else default,
        "requires_restart": False,
        "is_secret": secret,
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
            entry = _from_field(view.package, field)
            suggestions[entry["key"]] = entry

    registry = getattr(getattr(app.state, "settings", None), "registry", None)
    if registry is not None:
        for definition in registry.all_definitions:
            suggestions.setdefault(definition.key, _from_definition(definition))

    return [suggestions[key] for key in sorted(suggestions)]

"""Autocomplete for declared generic keys; module settings use their own editor.

Defaults are masked here because Browse renders them in its resolved-value panel.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from simple_module_core.module_settings import get_module_settings_registry
from simple_module_core.secret_fields import conceals_secret, mask


def _from_definition(definition) -> dict[str, Any]:
    """Mask declarations directly, as module fields are no longer suggested."""
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
    """Declared generic keys only; registered module packages use their editor."""
    suggestions: dict[str, dict[str, Any]] = {}
    modules = get_module_settings_registry(app)
    registry = getattr(getattr(app.state, "settings", None), "registry", None)
    if registry is not None:
        for definition in registry.all_definitions:
            package, sep, _ = definition.key.partition(".")
            if sep and modules is not None and modules.get(package) is not None:
                continue
            suggestions[definition.key] = _from_definition(definition)

    return [suggestions[key] for key in sorted(suggestions)]

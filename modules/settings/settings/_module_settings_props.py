"""Serialize module-settings views into Inertia props.

Split from ``_module_settings`` (collection) so each file keeps one
responsibility: that one discovers and shapes the views, this one is the
boundary where a settings object stops being Python and becomes a prop.
"""

from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder

from settings._module_settings import ModuleSettingsView


def serialize(views: list[ModuleSettingsView]) -> list[dict[str, Any]]:
    """Convert dataclass views to plain dicts for Inertia props.

    Field values arrive as whatever type the module declared — pydantic has
    already coerced ``media_root: Path`` to a ``PosixPath``, ``timeout:
    timedelta`` to a ``timedelta`` — and this screen reflects every installed
    module's settings, so the set of types is open-ended by design. They are
    encoded here rather than handed on as-is.
    """
    return [
        {
            "module_name": v.module_name,
            "package": v.package,
            "env_prefix": v.env_prefix,
            "class_name": v.class_name,
            "manage_url": v.manage_url,
            "fields": [
                {
                    "name": f.name,
                    "env_var": f.env_var,
                    "value": jsonable_encoder(f.value),
                    "default": jsonable_encoder(f.default),
                    "description": f.description,
                    "is_secret": f.is_secret,
                    "type": f.type,
                    "requires_restart": f.requires_restart,
                    "group": f.group,
                    "env_set": f.env_set,
                    "db_override": f.db_override,
                    "source": f.source,
                }
                for f in v.fields
            ],
        }
        for v in views
    ]

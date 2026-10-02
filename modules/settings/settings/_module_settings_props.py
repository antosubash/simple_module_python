"""Serialize module-settings views into Inertia props.

Split from ``_module_settings`` (collection) so each file keeps one
responsibility: that one discovers and shapes the views, this one is the
boundary where a settings object stops being Python and becomes a prop.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder

from settings._module_settings import ModuleSettingsView, _package_of


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
                    "env_readable": f.env_readable,
                    "db_override": f.db_override,
                    "source": f.source,
                    # Turns a pattern-constrained string into a select rather
                    # than a text box whose only feedback on a typo is a 422.
                    "choices": f.choices,
                }
                for f in v.fields
            ],
        }
        for v in views
    ]


def testable_packages(app: FastAPI) -> dict[str, list[str]]:
    """Package -> the names of the health checks its module registered.

    "Test connection" is just that module's health checks run on demand —
    reusing the registry means settings never learns what an SMTP or an S3
    connection is. The names come back with the packages so the button can say
    what it is about to dial ("Test mailer connection") instead of the useless
    "Test connection" a bare package list can produce.
    """
    checks_by_owner: dict[str, list[str]] = {}
    for check in app.state.sm.health_registry.all_checks:
        if check.module:
            checks_by_owner.setdefault(check.module, []).append(check.name)

    return {
        _package_of(mod): sorted(checks_by_owner[mod.meta.name])
        for mod in getattr(app.state.sm, "modules", ())
        if mod.meta.name in checks_by_owner
    }

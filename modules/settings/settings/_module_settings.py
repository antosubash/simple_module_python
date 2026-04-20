"""Autodiscover per-module pydantic ``BaseSettings`` attached to ``app.state``.

Framework convention (see ``CLAUDE.md`` and ``ModuleBase.register_settings``):
each module stores a services dataclass on ``app.state.<package_name>`` whose
``.settings`` attribute is a pydantic ``BaseSettings`` subclass. This helper
walks ``app.state.sm.modules``, derives the package name from
``type(mod).__module__``, pulls the settings object off the attached services,
and returns a serializable view for the admin UI.

Fields whose name matches ``_SECRET_PATTERNS`` are masked in the output so
secrets never reach the browser even read-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from pydantic_settings import BaseSettings

# Case-insensitive fragment match. We intentionally DON'T match the bare word
# "token" (would mask `verification_token_lifetime_seconds` — just an int) or
# "key" alone (would mask `s3_bucket_key_prefix` etc.). Instead we require a
# marker that actually indicates material: "password", "secret", "api_key",
# "private_key", or the composite "token_secret" used by fastapi-users.
_SECRET_PATTERNS = re.compile(
    r"(password|secret|api[_-]?key|private[_-]?key|token[_-]?secret)", re.I
)
_SECRET_MASK = "••••••••"


@dataclass(frozen=True, slots=True)
class ModuleSettingField:
    name: str
    env_var: str
    value: Any
    default: Any
    description: str
    is_secret: bool


@dataclass(frozen=True, slots=True)
class ModuleSettingsView:
    module_name: str
    package: str
    env_prefix: str
    class_name: str
    fields: list[ModuleSettingField]


def _mask(value: Any) -> Any:
    if value in (None, "", [], {}):
        return value
    return _SECRET_MASK


def _env_prefix_of(settings: BaseSettings) -> str:
    cfg = getattr(settings, "model_config", None)
    if isinstance(cfg, dict):
        return str(cfg.get("env_prefix", "") or "")
    return str(getattr(cfg, "env_prefix", "") or "")


def _package_of(mod: Any) -> str:
    """Return the top-level package name of a module instance (e.g. "users").

    ``type(mod).__module__`` is typically ``"<pkg>.module"`` — take the first
    segment.
    """
    dotted = type(mod).__module__
    return dotted.split(".", 1)[0]


def _extract_settings(app: FastAPI, package: str) -> BaseSettings | None:
    """Return the ``BaseSettings`` instance attached to ``app.state.<package>``.

    The services dataclass exposes it as ``.settings``. We also accept the
    rare case where the module stashes the settings object directly.
    """
    services = getattr(app.state, package, None)
    if services is None:
        return None
    if isinstance(services, BaseSettings):
        return services
    inner = getattr(services, "settings", None)
    return inner if isinstance(inner, BaseSettings) else None


def _field_view(name: str, settings: BaseSettings, prefix: str) -> ModuleSettingField:
    info = type(settings).model_fields[name]
    raw_value = getattr(settings, name)
    is_secret = bool(_SECRET_PATTERNS.search(name))
    return ModuleSettingField(
        name=name,
        env_var=f"{prefix}{name.upper()}",
        value=_mask(raw_value) if is_secret else raw_value,
        default=_mask(info.default) if is_secret else info.default,
        description=info.description or "",
        is_secret=is_secret,
    )


def collect_module_settings(app: FastAPI) -> list[ModuleSettingsView]:
    """Return a sorted, serializable view of every module's BaseSettings."""
    views: list[ModuleSettingsView] = []
    modules = getattr(app.state.sm, "modules", ())
    for mod in modules:
        package = _package_of(mod)
        settings = _extract_settings(app, package)
        if settings is None:
            continue
        fields = [
            _field_view(name, settings, _env_prefix_of(settings))
            for name in type(settings).model_fields
        ]
        views.append(
            ModuleSettingsView(
                module_name=mod.meta.name,
                package=package,
                env_prefix=_env_prefix_of(settings),
                class_name=type(settings).__name__,
                fields=fields,
            )
        )
    views.sort(key=lambda v: v.module_name)
    return views


def serialize(views: list[ModuleSettingsView]) -> list[dict[str, Any]]:
    """Convert dataclass views to plain dicts for Inertia props."""
    return [
        {
            "module_name": v.module_name,
            "package": v.package,
            "env_prefix": v.env_prefix,
            "class_name": v.class_name,
            "fields": [
                {
                    "name": f.name,
                    "env_var": f.env_var,
                    "value": f.value,
                    "default": f.default,
                    "description": f.description,
                    "is_secret": f.is_secret,
                }
                for f in v.fields
            ],
        }
        for v in views
    ]

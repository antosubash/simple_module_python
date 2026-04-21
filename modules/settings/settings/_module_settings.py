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

from settings.hydrate import value_type_for_field

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
    type: str
    requires_restart: bool
    group: str | None


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
    cls = type(settings)
    info = cls.model_fields[name]
    raw_value = getattr(settings, name)
    is_secret = bool(_SECRET_PATTERNS.search(name))
    extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
    return ModuleSettingField(
        name=name,
        env_var=f"{prefix}{name.upper()}",
        value=_mask(raw_value) if is_secret else raw_value,
        default=_mask(info.default) if is_secret else info.default,
        description=info.description or "",
        is_secret=is_secret,
        type=value_type_for_field(cls, name),
        requires_restart=bool(extra.get("requires_restart", False)),
        group=extra.get("group"),
    )


def collect_module_settings(app: FastAPI) -> list[ModuleSettingsView]:
    """Return a sorted, serializable view of every module's BaseSettings.

    Iterates ``app.state.sm.modules`` for plugin modules, then folds in any
    additional packages recorded in ``app.state.settings.module_registry``
    (e.g. ``"host"``) that aren't backed by a ``ModuleBase`` instance.
    """
    views: list[ModuleSettingsView] = []
    seen: set[str] = set()

    modules = getattr(app.state.sm, "modules", ())
    for mod in modules:
        package = _package_of(mod)
        settings = _extract_settings(app, package)
        if settings is None:
            continue
        views.append(_build_view(mod.meta.name, package, settings))
        seen.add(package)

    settings_services = getattr(app.state, "settings", None)
    registry = getattr(settings_services, "module_registry", None)
    if registry is not None:
        for package in registry.all_packages():
            if package in seen:
                continue
            settings = _extract_settings(app, package)
            if settings is None:
                continue
            views.append(_build_view(package.title(), package, settings))
            seen.add(package)

    views.sort(key=lambda v: v.module_name)
    return views


def _build_view(module_name: str, package: str, settings: BaseSettings) -> ModuleSettingsView:
    prefix = _env_prefix_of(settings)
    fields = [_field_view(name, settings, prefix) for name in type(settings).model_fields]
    return ModuleSettingsView(
        module_name=module_name,
        package=package,
        env_prefix=prefix,
        class_name=type(settings).__name__,
        fields=fields,
    )


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
                    "type": f.type,
                    "requires_restart": f.requires_restart,
                    "group": f.group,
                }
                for f in v.fields
            ],
        }
        for v in views
    ]

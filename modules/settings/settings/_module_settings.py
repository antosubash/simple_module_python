"""Autodiscover per-module pydantic ``BaseSettings`` attached to ``app.state``.

Each module stores a services dataclass on ``app.state.<package>`` whose
``.settings`` attribute is a pydantic ``BaseSettings`` subclass.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from pydantic_settings import BaseSettings

from settings.env_vars import env_prefix_for
from settings.hydrate import value_type_for_field
from settings.service import SettingService

# We intentionally DON'T match the bare word "token" (would mask
# `verification_token_lifetime_seconds` — just an int) or "key" alone (would
# mask `s3_bucket_key_prefix`). Only fragments that actually indicate material.
_SECRET_PATTERNS = re.compile(
    r"(password|secret|api[_-]?key|private[_-]?key|token[_-]?secret)", re.I
)
SECRET_MASK = "••••••••"


def is_secret_field(name: str) -> bool:
    """True if a field name suggests it holds credential material."""
    return bool(_SECRET_PATTERNS.search(name))


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
    env_set: bool = False
    """This field is genuinely env-readable *and* its env var is set.

    Deliberately not "the ``SM_*`` label below is present in ``os.environ``".
    The bundled module settings classes declare no ``env_prefix`` — they are
    constructed from pydantic defaults and hydrated from the DB — so their
    ``SM_*`` vars are never consulted. Reporting a leftover
    ``SM_USERS_SMTP_HOST`` as the live source would invert the very question
    this screen answers. Classes that *do* declare one (the host's ``Settings``
    with ``SM_``, and anything from the module scaffold) report ``env`` for
    real, because for them pydantic really does read it.
    """
    db_override: bool = False
    """A stored setting overrides this field."""

    @property
    def source(self) -> str:
        """Where the live value came from: ``db``, ``env`` or ``default``.

        Mirrors the precedence in ``hydrate_settings``: DB overrides are passed
        to the constructor explicitly, so they beat anything pydantic reads for
        fields left unset, which in turn beats the field default. ``env`` only
        appears for settings classes that actually declare an ``env_prefix``;
        see :attr:`env_set`. Showing this is the difference between "why is
        this not taking effect" being a five-minute question and an afternoon.
        """
        if self.db_override:
            return "db"
        if self.env_set:
            return "env"
        return "default"


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
    return SECRET_MASK


def _package_of(mod: Any) -> str:
    return type(mod).__module__.split(".", 1)[0]


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


def _resolve_default(info) -> Any:
    """Return the effective default, handling ``default_factory`` fields.

    Pydantic sets ``info.default`` to ``PydanticUndefined`` when
    ``default_factory`` is used. We call the factory to get the concrete
    default so the settings UI can serialize it.
    """
    from pydantic_core import PydanticUndefined

    if info.default is not PydanticUndefined:
        return info.default
    if info.default_factory is not None:
        return info.default_factory()
    return None


def _env_readable_var(settings: BaseSettings, name: str) -> str | None:
    """Env var pydantic would actually read for ``name``, or ``None``.

    ``env_var`` on the view is a *label* — the ``SM_<PACKAGE>_<FIELD>`` name the
    ``smpy settings import-from-env`` CLI looks for, kept from before settings
    moved into the DB. It is not evidence that pydantic reads it: the bundled
    module settings classes declare ``SettingsConfigDict(extra="ignore")`` with
    no ``env_prefix``, so ``SM_FILE_STORAGE_BACKEND`` has no effect on
    ``FileStorageSettings()``. Deriving env-readability from the class's own
    ``env_prefix`` keeps the "From environment" badge honest, and works as-is
    for the classes that do declare one — the host's ``Settings`` (``SM_``) and
    every module built from the scaffold, whose template ships
    ``env_prefix="SM_<PACKAGE>_"``.
    """
    env_prefix = str(type(settings).model_config.get("env_prefix") or "")
    if not env_prefix:
        return None
    return f"{env_prefix}{name.upper()}"


def _field_view(
    name: str,
    settings: BaseSettings,
    prefix: str,
    overridden: frozenset[str] = frozenset(),
) -> ModuleSettingField:
    cls = type(settings)
    info = cls.model_fields[name]
    raw_value = getattr(settings, name)
    secret = is_secret_field(name)
    extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
    default = _resolve_default(info)
    env_var = f"{prefix}{name.upper()}"
    live_env_var = _env_readable_var(settings, name)
    return ModuleSettingField(
        name=name,
        env_var=env_var,
        value=_mask(raw_value) if secret else raw_value,
        default=_mask(default) if secret else default,
        description=info.description or "",
        is_secret=secret,
        type=value_type_for_field(cls, name),
        requires_restart=bool(extra.get("requires_restart", False)),
        group=extra.get("group"),
        env_set=live_env_var is not None and live_env_var in os.environ,
        db_override=name in overridden,
    )


def collect_module_settings(
    app: FastAPI,
    overrides: dict[str, frozenset[str]] | None = None,
) -> list[ModuleSettingsView]:
    """Return a sorted, serializable view of every module's BaseSettings.

    Folds in both ``app.state.sm.modules`` (plugin modules) and additional
    packages registered via ``app.state.settings.module_registry`` (e.g.
    ``"host"``) that aren't backed by a ``ModuleBase`` instance.

    ``overrides`` maps package -> field names carrying a stored override. It
    is passed in rather than read here because fetching it is async and this
    function is not; callers without it get ``db_override=False`` throughout.
    """
    by_package = overrides or {}
    views: list[ModuleSettingsView] = []
    seen: set[str] = set()

    for mod in getattr(app.state.sm, "modules", ()):
        package = _package_of(mod)
        settings = _extract_settings(app, package)
        if settings is None:
            continue
        views.append(_build_view(mod.meta.name, package, settings, by_package))
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
            views.append(_build_view(package.title(), package, settings, by_package))
            seen.add(package)

    views.sort(key=lambda v: v.module_name)
    return views


def _build_view(
    module_name: str,
    package: str,
    settings: BaseSettings,
    overrides: dict[str, frozenset[str]] | None = None,
) -> ModuleSettingsView:
    prefix = env_prefix_for(package)
    overridden = (overrides or {}).get(package, frozenset())
    fields = [
        _field_view(name, settings, prefix, overridden) for name in type(settings).model_fields
    ]
    return ModuleSettingsView(
        module_name=module_name,
        package=package,
        env_prefix=prefix,
        class_name=type(settings).__name__,
        fields=fields,
    )


async def overrides_by_package(service: SettingService) -> dict[str, frozenset[str]]:
    """Map package -> field names carrying a stored override.

    Reads the SYSTEM scope once and buckets by key prefix. Packages with no
    overrides are simply absent, which :func:`collect_module_settings` already
    treats as "nothing overridden". Shared by both the Inertia view and the
    JSON API so the two never drift on what "overridden" means.
    """
    from settings.store import SettingsStore

    return await SettingsStore(service).all_override_fields()


def serialize(views: list[ModuleSettingsView]) -> list[dict[str, Any]]:
    """Convert dataclass views to plain dicts for Inertia props.

    Field values arrive as whatever type the module declared — pydantic has
    already coerced ``media_root: Path`` to a ``PosixPath``, ``timeout:
    timedelta`` to a ``timedelta`` — and this screen reflects every installed
    module's settings, so the set of types is open-ended by design. They are
    encoded here rather than handed on as-is: this is the boundary where a
    settings object stops being Python and becomes a prop.
    """
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

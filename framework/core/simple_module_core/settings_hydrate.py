"""Resolve a module's settings class: env → DB overrides → pydantic defaults.

A field's declared Python type maps to one of the five ``value_type`` labels
the settings table stores (``string | bool | int | float | json``). The
hydrator reads overrides from an :class:`OverrideSource`, parses each according
to its stored ``value_type`` and constructs the class, so pydantic enforces
field validators and any ``@model_validator`` hooks.

Lives in the framework (#500): the hosting lifespan hydrates every registered
class at boot whether or not the ``settings`` plugin is enabled. The DB read
itself is behind :class:`OverrideSource`, which ``simple_module_db`` (direct
session reads) and the ``settings`` plugin (``SettingsStore``) both satisfy;
the sync worker twin, ``hydrate_settings_sync``, lives in
``simple_module_db.stored_settings`` because it needs a SQLAlchemy session.
"""

from __future__ import annotations

import logging
import types
from typing import Any, Literal, Protocol, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    InitSettingsSource,
    SecretsSettingsSource,
)

from simple_module_core.stored_settings import (
    RELATED_FIELDS_CTX,
    construct_leniently,
    parse_stored_value,
)

logger = logging.getLogger(__name__)

_SCALAR_TYPES = {bool: "bool", int: "int", float: "float"}

# Re-exported: modules raise cross-field errors with it (``background_tasks``).
__all__ = [
    "RELATED_FIELDS_CTX",
    "OverrideSource",
    "build_settings",
    "env_supplied_fields",
    "hydrate_settings",
    "input_type_for_field",
    "value_type_for_field",
]


class OverrideSource(Protocol):
    """Where stored overrides come from: ``{field_name: (raw, value_type)}``."""

    async def get_overrides(self, package: str) -> dict[str, tuple[str, str]]: ...


def value_type_for_field(cls: type[BaseSettings], field_name: str) -> str:
    """Return the ``value_type`` label for a field based on its annotation.

    - ``bool`` → ``"bool"``
    - ``int`` → ``"int"``
    - ``float`` → ``"float"``
    - ``str``, enums and ``Literal`` of strings → ``"string"``
    - ``list``, ``dict``, and other container types → ``"json"``
    """
    info = cls.model_fields[field_name]
    ann = info.annotation
    origin = get_origin(ann)
    if origin is Literal and all(isinstance(a, str) for a in get_args(ann)):
        return "string"
    if origin is not None:
        return "json"
    return _SCALAR_TYPES.get(ann, "string")


def _holds_structure(ann: object) -> bool:
    """A bare ``dict``/``list``/model: not editable as a single-line string."""
    return isinstance(ann, type) and issubclass(
        ann, dict | list | set | frozenset | tuple | BaseModel
    )


def input_type_for_field(cls: type[BaseSettings], field_name: str) -> tuple[str, bool]:
    """``(input_type, nullable)`` — which editor control a field needs.

    Storage stays on :func:`value_type_for_field`, which files every union
    under ``json``. That is right for the store and wrong for the form:
    ``int | None`` wants a number box where empty means ``None``, not a JSON
    textarea that shows the literal text ``null`` (GH #487).
    """
    ann = cls.model_fields[field_name].annotation
    if get_origin(ann) not in (Union, types.UnionType):
        return value_type_for_field(cls, field_name), False
    args = get_args(ann)
    rest = [a for a in args if a is not type(None)]
    nullable = len(rest) < len(args)
    if len(rest) == 1 and get_origin(rest[0]) is None:
        only = rest[0]
        if _holds_structure(only):
            return "json", nullable
        return _SCALAR_TYPES.get(only, "string"), nullable
    return "json", nullable


def env_supplied_fields(cls: type[BaseSettings]) -> frozenset[str]:
    """Fields the class's own non-init sources (env, ``.env``, secrets) answer.

    Asks the sources ``cls`` actually installs, so a ``DbBackedSettings``
    (init-only) reports nothing and an ``env_prefix`` class reports exactly the
    ``<PREFIX><FIELD>`` names that are set. Deliberately not ``cls()``: a
    model validator can reject the env-only view (a production broker check)
    that the DB-merged one would pass.

    A class with no ``env_prefix`` reports nothing from its sources: a plain
    ``BaseSettings`` reads bare, case-insensitive names, so a field called
    ``user``, ``home`` or ``path`` would be pinned by the process environment
    and every admin edit refused. Only its ``env_seeded_fields`` count.
    """
    found: set[str] = set()
    if cls.model_config.get("env_prefix"):
        found.update(_source_supplied_fields(cls))
    # A class may also read env through a ``default_factory`` (one shared
    # variable seeding several fields), which no source can see. It names
    # those fields itself, so env still beats the DB for them.
    seeded = getattr(cls, "env_seeded_fields", None)
    if callable(seeded):
        found.update(seeded())
    return frozenset(found) & cls.model_fields.keys()


def _source_supplied_fields(cls: type[BaseSettings]) -> set[str]:
    sources = cls.settings_customise_sources(
        cls,
        init_settings=InitSettingsSource(cls, init_kwargs={}),
        env_settings=EnvSettingsSource(cls),
        dotenv_settings=DotEnvSettingsSource(cls),
        file_secret_settings=SecretsSettingsSource(cls),
    )
    by_key = {(info.alias or name): name for name, info in cls.model_fields.items()}
    found: set[str] = set()
    for source in sources:
        if isinstance(source, InitSettingsSource):
            continue
        found.update(by_key.get(key, key) for key in source())
    return found


def build_settings[T: BaseSettings](
    cls: type[T], raw_overrides: dict[str, tuple[str, str]], *, lenient: bool = False
) -> T:
    """Construct ``cls`` from ``{field: (raw, value_type)}``, skipping unknown fields.

    Shared by the async and sync hydrators so parsing cannot drift.

    Strict by default: an invalid stored value raises, which is what a settings
    write relies on to answer 422. ``lenient=True`` is for *boot* paths (web
    lifespan, workers): a row that was stored before a validator tightened must
    not take the app down, nor discard the module's other, valid overrides. Each
    offending field is logged and ignored (it falls back to env/default).

    Precedence is env → DB → default (GH #486). pydantic-settings ranks init
    kwargs above its env source, so a stored override for a field the
    environment sets is dropped here rather than passed in.
    """
    from_env = env_supplied_fields(cls)
    parsed: dict[str, Any] = {}
    for field_name, (raw, vtype) in raw_overrides.items():
        if field_name not in cls.model_fields or field_name in from_env:
            continue
        try:
            parsed[field_name] = parse_stored_value(raw, vtype)
        except ValueError:
            if not lenient:
                raise
            logger.error(
                "Ignoring stored %s.%s: cannot parse as %s", cls.__name__, field_name, vtype
            )
    if not lenient:
        return cls(**parsed)
    return construct_leniently(cls, parsed, level=logging.ERROR)


async def hydrate_settings[T: BaseSettings](
    cls: type[T], source: OverrideSource, package: str, *, lenient: bool = False
) -> T:
    """Construct ``cls`` with ``source``'s overrides merged over pydantic defaults."""
    return build_settings(cls, await source.get_overrides(package), lenient=lenient)

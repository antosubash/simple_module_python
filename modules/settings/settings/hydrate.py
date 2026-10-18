"""Resolve a module's BaseSettings from DB overrides + pydantic defaults.

A field's declared Python type maps to one of the five ``value_type`` labels
understood by SettingsStore (``string | bool | int | float | json``). The
hydrator reads overrides, parses each according to its stored ``value_type``,
and constructs the BaseSettings — pydantic enforces field validators and any
``@model_validator`` hooks.
"""

from __future__ import annotations

import json
import logging
import types
from typing import Union, get_args, get_origin

from pydantic import ValidationError
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    InitSettingsSource,
    SecretsSettingsSource,
)
from sqlalchemy.orm import Session

from settings.store import SettingsStore, get_overrides_sync

logger = logging.getLogger(__name__)

_SCALAR_TYPES = {bool: "bool", int: "int", float: "float"}


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
    return _SCALAR_TYPES.get(ann, "string")


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
        return _SCALAR_TYPES.get(rest[0], "string"), nullable
    return "json", nullable


def _parse(raw: str, value_type: str):
    if value_type == "bool":
        return raw.lower() in ("1", "true", "yes", "on")
    if value_type == "int":
        return int(raw)
    if value_type == "float":
        return float(raw)
    if value_type == "json":
        return json.loads(raw)
    return raw


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
    parsed: dict[str, object] = {}
    for field_name, (raw, vtype) in raw_overrides.items():
        if field_name not in cls.model_fields or field_name in from_env:
            continue
        try:
            parsed[field_name] = _parse(raw, vtype)
        except ValueError:
            if not lenient:
                raise
            logger.error(
                "Ignoring stored %s.%s: cannot parse as %s", cls.__name__, field_name, vtype
            )
    if not lenient:
        return cls(**parsed)
    try:
        return cls(**parsed)
    except ValidationError as exc:
        bad = {str(e["loc"][0]) for e in exc.errors() if e["loc"]} & parsed.keys()
        if not bad:
            raise
        for name in sorted(bad):
            logger.error(
                "Ignoring stored value for %s.%s: it no longer validates (%s)",
                cls.__name__,
                name,
                # error *types* only: a validator's message may echo the value (a secret)
                ", ".join(str(e["type"]) for e in exc.errors() if e["loc"][:1] == (name,)),
            )
        return cls(**{k: v for k, v in parsed.items() if k not in bad})


async def hydrate_settings[T: BaseSettings](
    cls: type[T], store: SettingsStore, package: str, *, lenient: bool = False
) -> T:
    """Construct ``cls`` with DB overrides merged over pydantic defaults."""
    return build_settings(cls, await store.get_overrides(package), lenient=lenient)


def hydrate_settings_sync[T: BaseSettings](
    cls: type[T], session: Session, package: str, *, lenient: bool = False
) -> T:
    """Sync :func:`hydrate_settings` for Celery workers and other non-async code.

    Workers never run the hosting lifespan, so a bare ``cls()`` there returns
    pydantic defaults (``DbBackedSettings`` ignores the environment on purpose).
    Takes a plain sync ``Session`` and applies the same SYSTEM-scope overrides
    with the same ``value_type`` parsing as the web process.
    """
    return build_settings(cls, get_overrides_sync(session, package), lenient=lenient)

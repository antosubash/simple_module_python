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
from typing import get_origin

from pydantic import ValidationError
from pydantic_settings import BaseSettings
from sqlalchemy.orm import Session

from settings.store import SettingsStore, get_overrides_sync

logger = logging.getLogger(__name__)


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
    if ann is bool:
        return "bool"
    if ann is int:
        return "int"
    if ann is float:
        return "float"
    return "string"


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
    """
    parsed: dict[str, object] = {}
    for field_name, (raw, vtype) in raw_overrides.items():
        if field_name not in cls.model_fields:
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
                "; ".join(str(e["msg"]) for e in exc.errors() if e["loc"][:1] == (name,)),
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

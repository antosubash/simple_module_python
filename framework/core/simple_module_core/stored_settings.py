"""Decode stored setting values and build a settings class from them leniently.

Shared by the two places that turn ``settings_setting`` rows into a settings
object: the hosting layer's pre-app read (``_preapp_config``), which runs
before any module is importable as a plugin, and the module-settings
hydrator (``simple_module_core.settings_hydrate``). One copy keeps the two
parsers from drifting.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError
from pydantic_core import ErrorDetails, InitErrorDetails, PydanticCustomError
from pydantic_core import ValidationError as CoreValidationError
from pydantic_settings import BaseSettings

__all__ = [
    "RELATED_FIELDS_CTX",
    "construct_leniently",
    "field_error",
    "parse_stored_value",
]

logger = logging.getLogger(__name__)

#: ``ctx`` key on a validation error listing the *other* fields a cross-field
#: rule depends on; raise it with ``PydanticCustomError(type, msg, {key: [...]})``.
#: Lenient construction drops those when the reported field is not stored.
RELATED_FIELDS_CTX = "related_fields"

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def field_error(
    model: type,
    field: str,
    error_type: str,
    message: str,
    *,
    value: Any = None,
    related: list[str] | tuple[str, ...] = (),
) -> CoreValidationError:
    """A cross-field failure from a ``model_validator``, located on ``field``.

    A bare ``ValueError`` from a model validator has ``loc=()``: the settings
    form cannot show it and lenient hydration cannot tell which stored field to
    drop (#558). This pins the error on ``field`` and names every field the rule
    reads under ``ctx[RELATED_FIELDS_CTX]``. ``message`` is used verbatim.
    """
    return CoreValidationError.from_exception_data(
        title=model.__name__,
        line_errors=[
            InitErrorDetails(
                type=PydanticCustomError(error_type, message, {RELATED_FIELDS_CTX: list(related)}),  # ty: ignore[invalid-argument-type]
                loc=(field,),
                input=value,
            )
        ],
    )


def parse_stored_value(raw: str, value_type: str) -> Any:
    """Decode a stored value according to its ``value_type`` label.

    The five labels (``string | bool | int | float | json``) are a stable
    stored format. Raises ``ValueError`` (``JSONDecodeError`` is one) on a
    value that does not decode — a boolean token included. Anything but a
    known true/false spelling used to read as ``False``, so a typo such as
    ``"tru"`` switched ``multi_tenant`` or ``maintenance_mode`` off with no
    trace; now the boot paths drop the row and warn instead.
    """
    if value_type == "bool":
        token = raw.strip().lower()
        if token in _TRUE:
            return True
        if token in _FALSE:
            return False
        raise ValueError("not a boolean token")
    if value_type == "int":
        return int(raw)
    if value_type == "float":
        return float(raw)
    if value_type == "json":
        return json.loads(raw)
    return raw


def construct_leniently[T: BaseSettings](
    cls: type[T],
    stored: dict[str, Any],
    *,
    fixed: dict[str, Any] | None = None,
    level: int = logging.WARNING,
) -> T:
    """``cls(**fixed, **stored)``, dropping each stored field that fails validation.

    For boot paths: a row written before a ``Literal`` or range narrowed must
    not take every worker down, nor discard the class's other, valid stored
    values. Each dropped field is logged at ``level`` by name and error type —
    never the message, which may echo the value (a secret) — and falls back to
    env/default. ``fixed`` values (not from the store) are never dropped; an
    error that names no stored field re-raises.
    """
    fixed = fixed or {}
    kept = dict(stored)
    while True:
        try:
            return cls(**fixed, **kept)
        except ValidationError as exc:
            culprits = {name: err["type"] for err in exc.errors() for name in _culprits(err, kept)}
            if not culprits:
                raise
            for name in sorted(culprits):
                logger.log(
                    level,
                    "Ignoring stored value for %s.%s: it no longer validates (%s)",
                    cls.__name__,
                    name,
                    culprits[name],
                )
            # Each pass removes at least one stored field, so this ends; a second
            # pass catches a rule that only fails once the first culprit is gone.
            kept = {k: v for k, v in kept.items() if k not in culprits}


def _culprits(error: ErrorDetails, stored: dict[str, Any]) -> list[str]:
    """The stored keys to drop so that ``error`` goes away.

    The field the error is reported on, when its value came from the store.
    Otherwise — that field is env-pinned, defaulted, or the error is
    model-level — the stored fields the validator names under
    ``ctx[RELATED_FIELDS_CTX]`` (#548).
    """
    loc = str(error["loc"][0]) if error["loc"] else None
    if loc in stored:
        return [loc]
    related = (error.get("ctx") or {}).get(RELATED_FIELDS_CTX, ())
    return [name for name in related if name in stored]

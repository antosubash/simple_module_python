"""Shared conversion of validation errors to Inertia form errors."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

# The first ``loc`` segment FastAPI adds to a RequestValidationError.
_REQUEST_SOURCES = frozenset({"body", "query", "path", "header", "cookie"})
_SURROGATES = re.compile(r"[\ud800-\udfff]")


def _escape_surrogates(text: str) -> str:
    # Keys must stay distinct: U+FFFD would merge "\ud800" and "\udfff".
    return _SURROGATES.sub(lambda m: f"\\u{ord(m.group()):04x}", text)


def sanitize_error_payload(value: Any) -> Any:
    """Make JSON-shaped error data encodable: U+FFFD in values, escapes in keys."""
    if isinstance(value, str):
        return _SURROGATES.sub("\ufffd", value)
    if isinstance(value, dict):
        return {
            (_escape_surrogates(key) if isinstance(key, str) else key): sanitize_error_payload(
                child
            )
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_error_payload(child) for child in value]
    return value


def errors_from_validation(
    errors: Iterable[Mapping[str, Any]], *, request_source: bool = False
) -> dict[str, str]:
    """Keep the first message for each top-level form field.

    Union-member tags (``("quantity", "int")``), list indices and nested-model
    segments never become keys. ``request_source`` drops the leading
    ``body``/``query``/… segment of a FastAPI ``RequestValidationError``; a
    plain ``model_validate`` error has none, so a field really named ``path``
    keeps its key.
    """
    result: dict[str, str] = {}
    for error in errors:
        loc = tuple(error["loc"])
        if request_source and loc and loc[0] in _REQUEST_SOURCES:
            loc = loc[1:]
        field = str(loc[0]) if loc else "general"
        result.setdefault(field, error["msg"])
    return result


def scope_errors(errors: dict[str, str], bag: str | None) -> dict[str, Any]:
    """Nest ``errors`` under the ``X-Inertia-Error-Bag`` name when one is set.

    An empty header counts as unset, matching ``InertiaRequest.error_bag``.
    """
    return {bag: errors} if bag else errors

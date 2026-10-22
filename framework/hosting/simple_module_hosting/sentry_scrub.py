"""Scrub secrets and PII out of a serialized Sentry event before it is sent.

The SDK's own ``EventScrubber`` matches exact key names, is not recursive and
never looks at ``contexts`` or free text, so this runs a second, stricter
pass from ``before_send``/``before_send_transaction``:

* targeted passes first: request cookies, bodies and the WSGI/ASGI ``env``
  (``REMOTE_ADDR``) are dropped, sensitive headers removed outright, URL and
  transaction paths lose id-shaped segments, ``user`` keeps only ``id``;
* then *every* top-level field goes through :func:`scrub` (deny by default:
  a field the SDK adds later is covered without a code change): mapping keys
  matching :data:`SENSITIVE_KEY` and ``[key, value]`` pairs whose key does
  have their value replaced at any depth; every string, bytes included, goes
  through :func:`scrub_text` (``key=value`` pairs, header lines,
  ``Bearer``/``Basic`` credentials, URL userinfo, JWTs, bare long tokens);
* Celery task ``args``/``kwargs``/return values, SQL parameters and frame
  locals are dropped wherever they appear.

Anything beyond :data:`_MAX_DEPTH` is replaced, so a cyclic or absurdly deep
structure ends in ``REDACTED`` instead of a ``RecursionError``. A scrubber
failure must never send the raw event: ``sentry.build_before_send`` drops it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from simple_module_hosting.sentry_scrub_text import (
    REDACTED,
    SENSITIVE_KEY,
    is_sensitive_key,
    scrub_text,
)

__all__ = ["REDACTED", "SENSITIVE_KEY", "is_sensitive_key", "scrub", "scrub_event", "scrub_text"]

_MAX_DEPTH = 12
_PATH_SEP = "/"
_PATH_PLACEHOLDER = "*"
_SOURCE_URL = "url"
_URL_KEY = "url"
_USER_ID = "id"
_PAIR_LEN = 2
# Celery's integration and its trace log records attach the task payload; SQL
# integrations attach bound parameters; ``vars`` are frame locals.
_DROP_KEYS = frozenset({"args", "kwargs", "return_value", "db.params", "db.sql.params", "vars"})
_REQUEST_DROP = ("cookies", "data", "env")
# Sentry's own correlation ids look like long hex tokens; keep them intact.
_ID_KEYS = frozenset({"event_id", "trace_id", "span_id", "parent_span_id", "request_id", "release"})
_ID_VALUE = re.compile(r"[\w.\-@+]{1,128}")
_ID_SEGMENT = re.compile(
    r"^(?:\d+|[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}"
    r"|(?=[\w\-]*\d)(?=[\w\-]*[A-Za-z])[\w\-]{20,})$",
    re.IGNORECASE,
)

Event = dict[str, Any]


def _scrub_entry(key: Any, value: Any, depth: int) -> Any:
    if is_sensitive_key(key):
        return REDACTED
    if key in _ID_KEYS and isinstance(value, str) and _ID_VALUE.fullmatch(value):
        return value
    if key == _URL_KEY and isinstance(value, str):
        return _scrub_url(value)
    return scrub(value, depth + 1)


def scrub(value: Any, depth: int = 0) -> Any:
    """Recursively redact sensitive keys and pairs and scrub every string."""
    if depth > _MAX_DEPTH:
        return REDACTED
    if isinstance(value, Mapping):
        return {k: _scrub_entry(k, v, depth) for k, v in value.items() if k not in _DROP_KEYS}
    if isinstance(value, list | tuple | set | frozenset):
        items = list(value)
        # Header and query lists: [["Authorization", "..."], ("Set-Cookie", "...")]
        if len(items) == _PAIR_LEN and is_sensitive_key(items[0]):
            return [scrub(items[0], depth + 1), REDACTED]
        return [scrub(v, depth + 1) for v in items]
    if isinstance(value, bytes | bytearray):
        return scrub_text(bytes(value).decode("utf-8", "replace"))
    if isinstance(value, str):
        return scrub_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    return scrub_text(repr(value))


def scrub_path(path: str) -> str:
    """Replace id- and token-shaped path segments with ``*``."""
    return _PATH_SEP.join(
        _PATH_PLACEHOLDER if _ID_SEGMENT.match(seg) else seg for seg in path.split(_PATH_SEP)
    )


def _scrub_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:  # e.g. an unbalanced IPv6 bracket: still scrub it as text
        return scrub_text(url)
    return scrub_text(urlunsplit(parts._replace(path=scrub_path(parts.path))))


def _is_sensitive_header(item: Any) -> bool:
    return isinstance(item, list | tuple) and len(item) == _PAIR_LEN and is_sensitive_key(item[0])


def _scrub_request(request: dict[str, Any]) -> None:
    for key in _REQUEST_DROP:
        request.pop(key, None)
    headers = request.get("headers")
    if isinstance(headers, Mapping):
        request["headers"] = {k: v for k, v in headers.items() if not is_sensitive_key(k)}
    elif isinstance(headers, list):
        request["headers"] = [h for h in headers if not _is_sensitive_header(h)]
    if isinstance(request.get(_URL_KEY), str):
        request[_URL_KEY] = _scrub_url(request[_URL_KEY])


def _scrub_user(event: Event) -> None:
    user = event.get("user")
    user_id = user.get(_USER_ID) if isinstance(user, Mapping) else None
    if user_id is None:
        event.pop("user", None)
    else:
        event["user"] = {_USER_ID: str(user_id)}  # never email/username/ip


def _scrub_transaction(event: Event) -> None:
    transaction = event.get("transaction")
    source = (event.get("transaction_info") or {}).get("source")
    if isinstance(transaction, str) and source == _SOURCE_URL:
        event["transaction"] = scrub_path(transaction)


def scrub_event(event: Event) -> Event:
    """Scrub ``event`` (in place where possible) and return it."""
    if isinstance(event.get("request"), dict):
        _scrub_request(event["request"])
    _scrub_user(event)
    _scrub_transaction(event)
    user = event.pop("user", None)
    scrubbed = scrub(event)
    event.clear()
    event.update(scrubbed)
    if user is not None:
        event["user"] = user
    return event

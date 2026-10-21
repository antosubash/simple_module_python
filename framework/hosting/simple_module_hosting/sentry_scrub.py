"""Scrub secrets and PII out of a serialized Sentry event before it is sent.

The SDK's own ``EventScrubber`` matches exact key names, is not recursive and
never looks at ``contexts`` or free text, so this runs a second, stricter
pass from ``before_send``/``before_send_transaction``:

* every mapping key matching :data:`SENSITIVE_KEY` (``password``, ``token``,
  ``authorization``, ``cookie``, ``session``, ``api_key``, ``csrf``, …, plus
  client-IP headers) has its value replaced, at any depth;
* free text (exception messages, log messages, breadcrumb data, span
  descriptions, URLs, query strings) has ``key=value`` pairs with a sensitive
  key, ``Bearer``/``Basic`` credentials and URL userinfo redacted;
* request cookies, bodies and the WSGI/ASGI ``env`` (``REMOTE_ADDR``) are
  dropped, sensitive headers removed outright;
* Celery task ``args``/``kwargs``/return values are dropped wherever they
  appear (the Celery integration's ``extra["celery-job"]`` and the
  ``extra["data"]`` the ``celery.app.trace`` log records carry);
* frame locals are dropped even though ``include_local_variables=False``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REDACTED = "[Filtered]"
_MAX_DEPTH = 12
_PATH_SEP = "/"
_PATH_PLACEHOLDER = "*"
_SOURCE_URL = "url"

_SENSITIVE_WORDS = (
    r"passw(?:or)?d|secret|token|authori[sz]ation|(?<![a-z])auth(?![a-z])|cookie|session|api[-_]?key|csrf|xsrf|credential"
    r"|private[-_]?key|signature|dsn"
    # client addresses are PII with send_default_pii=False
    r"|forwarded|real[-_]?ip|client[-_]?ip|remote[-_]?addr|ip[-_]?address"
)
SENSITIVE_KEY = re.compile(_SENSITIVE_WORDS, re.IGNORECASE)
# OAuth authorization codes travel as a bare ``code`` query parameter.
_EXACT_KEYS = frozenset({"code"})
_QUERY_CODE = re.compile(r"((?:^|[?&])code=)[^&#\s]*", re.IGNORECASE)
# Celery's integration and its trace log records attach the task payload.
_TASK_PAYLOAD_KEYS = frozenset({"args", "kwargs", "return_value"})

_KEY_VALUE = re.compile(
    rf"""(?P<key>["']?[\w.\-]*(?:{_SENSITIVE_WORDS})[\w.\-]*["']?\s*[=:]\s*)"""
    r"""(?P<quote>["']?)(?P<value>(?:Bearer\s+|Basic\s+)?[^\s&,;"'}\]]+)""",
    re.IGNORECASE,
)
_SCHEME_CREDENTIAL = re.compile(r"\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=\-]+", re.IGNORECASE)
_URL_USERINFO = re.compile(r"(?P<scheme>[a-z][a-z0-9+.\-]*://)[^/@\s]+@", re.IGNORECASE)
_ID_SEGMENT = re.compile(
    r"^(?:\d+|[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}"
    r"|(?=[\w\-]*\d)(?=[\w\-]*[A-Za-z])[\w\-]{20,})$",
    re.IGNORECASE,
)

Event = dict[str, Any]


def is_sensitive_key(key: object) -> bool:
    return isinstance(key, str) and (key.lower() in _EXACT_KEYS or bool(SENSITIVE_KEY.search(key)))


def scrub_text(text: str) -> str:
    """Redact credentials embedded in free text."""
    text = _URL_USERINFO.sub(rf"\g<scheme>{REDACTED}@", text)
    text = _QUERY_CODE.sub(rf"\g<1>{REDACTED}", text)
    text = _KEY_VALUE.sub(rf"\g<key>\g<quote>{REDACTED}", text)
    return _SCHEME_CREDENTIAL.sub(rf"\1 {REDACTED}", text)


def scrub(value: Any, depth: int = 0) -> Any:
    """Recursively redact sensitive keys and scrub every string."""
    if depth > _MAX_DEPTH:
        return REDACTED
    if isinstance(value, Mapping):
        return {
            k: REDACTED if is_sensitive_key(k) else scrub(v, depth + 1)
            for k, v in value.items()
            if k not in _TASK_PAYLOAD_KEYS
        }
    if isinstance(value, list | tuple):
        return [scrub(v, depth + 1) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def scrub_path(path: str) -> str:
    """Replace id- and token-shaped path segments with ``*``."""
    return _PATH_SEP.join(
        _PATH_PLACEHOLDER if _ID_SEGMENT.match(seg) else seg for seg in path.split(_PATH_SEP)
    )


def _scrub_url(url: str) -> str:
    parts = urlsplit(url)
    return scrub_text(urlunsplit(parts._replace(path=scrub_path(parts.path))))


def _scrub_request(request: dict[str, Any]) -> None:
    for key in ("cookies", "data", "env"):
        request.pop(key, None)
    headers = request.get("headers")
    if isinstance(headers, Mapping):
        request["headers"] = {
            k: scrub(v) for k, v in headers.items() if not is_sensitive_key(str(k))
        }
    query = request.get("query_string")
    if isinstance(query, str):
        request["query_string"] = scrub_text(query)
    elif query is not None:
        request["query_string"] = scrub(query)
    if isinstance(request.get("url"), str):
        request["url"] = _scrub_url(request["url"])


def _scrub_exceptions(event: Event) -> None:
    for exc in (event.get("exception") or {}).get("values") or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = scrub_text(exc["value"])
        _scrub_frames(exc)
    for thread in (event.get("threads") or {}).get("values") or []:
        _scrub_frames(thread)


def _scrub_frames(holder: Mapping[str, Any]) -> None:
    """Drop frame locals; scrub source context (a hard-coded secret is still one)."""
    for frame in (holder.get("stacktrace") or {}).get("frames") or []:
        frame.pop("vars", None)
        for key in ("pre_context", "context_line", "post_context"):
            if frame.get(key) is not None:
                frame[key] = scrub(frame[key])


def _scrub_spans(event: Event) -> None:
    for span in event.get("spans") or []:
        if isinstance(span.get("description"), str):
            span["description"] = scrub_text(span["description"])
        if isinstance(span.get("data"), Mapping):
            span["data"] = scrub(span["data"])


def _scrub_transaction(event: Event) -> None:
    transaction = event.get("transaction")
    source = (event.get("transaction_info") or {}).get("source")
    if isinstance(transaction, str) and source == _SOURCE_URL:
        event["transaction"] = scrub_text(scrub_path(transaction))


def scrub_event(event: Event) -> Event:
    """Scrub ``event`` in place (and return it)."""
    if isinstance(event.get("request"), dict):
        _scrub_request(event["request"])
    for key in ("extra", "contexts"):
        if isinstance(event.get(key), Mapping):
            event[key] = scrub(event[key])
    # Breadcrumbs: log messages and HTTP URLs/queries; logentry: log params.
    for key in ("breadcrumbs", "logentry", "message"):
        if event.get(key) is not None:
            event[key] = scrub(event[key])
    _scrub_exceptions(event)
    _scrub_spans(event)
    _scrub_transaction(event)
    return event

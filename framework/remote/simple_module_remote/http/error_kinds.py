"""Classify an error response, so the CLI only gives hints that fit it (#1241)."""

from __future__ import annotations

import json
import re
from http import HTTPStatus

__all__ = ["detail_of", "detail_text", "schema_mismatch", "token_problem"]

# Starlette's exact body for a path no route matches: a route or method mismatch
# signal. An endpoint raising a bare 404 looks identical; most domain 404s say
# "Not found" (resource_deps) or name what is missing, so the match is exact.
_ROUTE_NOT_FOUND = "Not Found"
# 422 error types that mean the request's shape differs from what the server expects.
# A value that failed validation is the caller's: unparseable (bool_parsing) or
# outside a constraint (too_short).
_SHAPE_ERRORS = frozenset({"missing", "extra_forbidden"})
# A 403 that is about the credential itself. The framework answers a bad or expired
# credential with 401, so a 403 only qualifies with one of these whole messages;
# "The invitation has expired" is about an invitation, not the token.
_CREDENTIAL_403 = re.compile(
    r"(forbidden|not authenticated|authentication required|invalid token"
    r"|token (has )?(expired|been revoked|revoked))\.?"
)


def detail_of(text: str) -> object:
    """The response body's ``detail`` as decoded JSON, else ``None``."""
    try:
        body = json.loads(text)
    except ValueError:
        return None
    return body.get("detail") if isinstance(body, dict) else None


_NOT_JSON = object()


def _decoded(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return _NOT_JSON


def _says_nothing(body: object) -> bool:
    if isinstance(body, dict):
        return all(value in (None, "") for value in body.values())
    return body in (None, [], "")


def detail_text(text: str) -> str:
    """The response's string ``detail``, else ``""``."""
    detail = detail_of(text)
    return detail if isinstance(detail, str) else ""


def token_problem(status: int, text: str) -> bool:
    """Whether logging in again could help: a 401, or a 403 about the credential.

    A 403 that explains a refusal of the action ("You cannot assign roles you do
    not hold.", a structured ``{"code": ...}``, or a plain-text body) came from a
    server that accepted the token.
    """
    if status == HTTPStatus.UNAUTHORIZED:
        return True
    detail = detail_of(text)
    if detail is None or (isinstance(detail, str) and not detail.strip()):
        body = _decoded(text)
        if body is _NOT_JSON or isinstance(body, str):
            detail = text if body is _NOT_JSON else body  # the body is the explanation
        elif isinstance(body, dict):
            # A blank detail or none: the other fields may still explain the refusal.
            return _says_nothing({k: v for k, v in body.items() if k != "detail"})
        else:
            return _says_nothing(body)
    if not isinstance(detail, str):
        return False
    wording = detail.strip().lower()
    return not wording or _CREDENTIAL_403.fullmatch(wording) is not None


def schema_mismatch(status: int, text: str) -> bool:
    """Whether the error suggests the CLI's schema no longer matches the server."""
    if status == HTTPStatus.METHOD_NOT_ALLOWED:
        return True
    detail = detail_of(text)
    if status == HTTPStatus.NOT_FOUND:
        return detail is None or detail == _ROUTE_NOT_FOUND
    if status == HTTPStatus.UNPROCESSABLE_ENTITY and isinstance(detail, list):
        return any(
            isinstance(error, dict)
            and isinstance(kind := error.get("type"), str)
            and kind in _SHAPE_ERRORS
            for error in detail
        )
    return False

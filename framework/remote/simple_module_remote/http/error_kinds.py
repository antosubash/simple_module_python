"""Classify an error response, so the CLI only gives hints that fit it (#1241)."""

from __future__ import annotations

import json
import re
from http import HTTPStatus

__all__ = ["detail_of", "detail_text", "schema_mismatch", "token_problem"]

# Starlette's exact body for a path no route matches. The framework's own domain
# 404s say "Not found" (resource_deps) or name what is missing, so the match is exact.
_ROUTE_NOT_FOUND = "Not Found"
# 422 error types that mean the request's shape differs from what the server expects.
# A value the server could not parse (bool_parsing, too_short, ...) is the caller's.
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


def detail_text(text: str) -> str:
    """The response's string ``detail``, else ``""``."""
    detail = detail_of(text)
    return detail if isinstance(detail, str) else ""


def token_problem(status: int, detail: object) -> bool:
    """Whether logging in again could help: a 401, or a 403 about the credential.

    A 403 that explains a refusal of the action ("You cannot assign roles you do
    not hold.", or a structured ``{"code": ...}``) came from a server that
    accepted the token.
    """
    if status == HTTPStatus.UNAUTHORIZED:
        return True
    if detail is None or (isinstance(detail, str) and not detail.strip()):
        return True
    if not isinstance(detail, str):
        return False
    return _CREDENTIAL_403.fullmatch(detail.strip().lower()) is not None


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

"""Classify an error response, so the CLI only gives hints that fit it (#1241)."""

from __future__ import annotations

import json
import re

__all__ = ["detail_text", "schema_mismatch", "token_problem"]

HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_METHOD_NOT_ALLOWED = 405
HTTP_UNPROCESSABLE = 422
# FastAPI's body for a path no route matches; a domain 404 names what is missing.
_ROUTE_NOT_FOUND = "not found"
# 422 error types that mean the request's shape differs from what the server expects.
# A value the server could not parse (bool_parsing, too_short, ...) is the caller's.
_SHAPE_ERRORS = frozenset({"missing", "extra_forbidden"})
# Wording of a 403 that is about the credential itself rather than the action.
_CREDENTIAL_WORDS = re.compile(
    r"authenticat|credential|expired|revoked|invalid token|unauthori[sz]ed|^forbidden$"
)


def _body(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return None


def detail_text(text: str) -> str:
    """The response's string ``detail``, else ``""``."""
    body = _body(text)
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail if isinstance(detail, str) else ""


def token_problem(status: int, detail: str) -> bool:
    """Whether logging in again could help: a 401, or a 403 about the credential.

    A 403 whose detail explains a refusal of the action ("You cannot assign roles
    you do not hold.") came from a server that accepted the token.
    """
    if status == HTTP_UNAUTHORIZED or not detail.strip():
        return True
    return _CREDENTIAL_WORDS.search(detail.strip().lower()) is not None


def schema_mismatch(status: int, text: str) -> bool:
    """Whether the error suggests the CLI's schema no longer matches the server."""
    if status == HTTP_METHOD_NOT_ALLOWED:
        return True
    body = _body(text)
    detail = body.get("detail") if isinstance(body, dict) else None
    if status == HTTP_NOT_FOUND:
        return detail is None or (isinstance(detail, str) and detail.lower() == _ROUTE_NOT_FOUND)
    if status == HTTP_UNPROCESSABLE and isinstance(detail, list):
        return any(isinstance(e, dict) and e.get("type") in _SHAPE_ERRORS for e in detail)
    return False

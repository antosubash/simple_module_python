"""Shared search-pattern helpers for LIKE/ILIKE filters."""

from __future__ import annotations

LIKE_ESCAPE_CHAR = "\\"


def _escape_like_term(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_contains_pattern(term: str) -> str:
    """Contains-match LIKE pattern with metacharacters escaped, so a literal
    ``%`` or ``_`` in a search term matches as text, not as a wildcard.

    Pair with ``ilike(pattern, escape=LIKE_ESCAPE_CHAR)`` (or ``like(...)``)
    so the escape character actually takes effect.
    """
    return f"%{_escape_like_term(term)}%"


def like_prefix_pattern(term: str) -> str:
    """Prefix-match LIKE pattern with metacharacters escaped, so a literal
    ``%`` or ``_`` in the prefix matches as text, not as a wildcard.

    Without this, a caller-supplied prefix containing ``%`` (e.g. a
    ``content_type`` family filter built from a query param) widens the match
    instead of narrowing it. Pair with ``ilike(pattern,
    escape=LIKE_ESCAPE_CHAR)`` (or ``like(...)``) so the escape character
    actually takes effect.
    """
    return f"{_escape_like_term(term)}%"

"""Shared search-pattern helpers for LIKE/ILIKE filters."""

from __future__ import annotations

LIKE_ESCAPE_CHAR = "\\"


def like_contains_pattern(term: str) -> str:
    """Contains-match LIKE pattern with metacharacters escaped, so a literal
    ``%`` or ``_`` in a search term matches as text, not as a wildcard.

    Pair with ``ilike(pattern, escape=LIKE_ESCAPE_CHAR)`` (or ``like(...)``)
    so the escape character actually takes effect.
    """
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"

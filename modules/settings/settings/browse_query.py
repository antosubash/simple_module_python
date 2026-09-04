"""Turn the store screen's query string into filters the service can run.

Every parameter here arrives from a url an admin may have typed, bookmarked or
kept open while the data moved underneath it. None of those are client errors
worth a 422 page — a broken link should still render the table — so each one
falls back to a sane value rather than rejecting the request. Clamping lives
here rather than in the view so the ``filters``/``pagination`` props can echo
exactly what the query ran with.
"""

from __future__ import annotations

from dataclasses import dataclass

from settings.constants import ALL_SCOPES, DEFAULT_PER_PAGE, MAX_PER_PAGE, SCOPE_ALL
from settings.contracts.schemas import SettingScope


@dataclass(frozen=True, slots=True)
class BrowseQuery:
    """Validated, clamped filters for one render of the raw store."""

    scope: str
    """A tab value: ``all`` or one of the real scopes."""
    q: str
    page: int
    per_page: int

    @property
    def scope_filter(self) -> SettingScope | None:
        """The scope to filter on, or ``None`` for the ``all`` tab."""
        return None if self.scope == SCOPE_ALL else SettingScope(self.scope)


def _int_or(raw: str, fallback: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def parse(scope: str, q: str, page: str, per_page: str) -> BrowseQuery:
    """Read the four query params, substituting defaults for anything unusable."""
    return BrowseQuery(
        scope=scope if scope in ALL_SCOPES else SCOPE_ALL,
        q=q,
        page=max(_int_or(page, 1), 1),
        per_page=max(1, min(_int_or(per_page, DEFAULT_PER_PAGE), MAX_PER_PAGE)),
    )

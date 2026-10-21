"""Query-string dependencies that build a ``simple_module_db.PageParams``.

Two flavours, because API and browser routes fail differently:

* ``PageParamsDep`` — strict. ``page < 1`` or ``per_page`` out of range is a
  422, for JSON APIs whose callers should fix their request.
* ``LenientPageParamsDep`` — for Inertia views reached from URLs people edit
  and bookmark. Garbage and out-of-range values clamp instead of rejecting.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query
from simple_module_db.pagination import DEFAULT_PER_PAGE, MAX_PER_PAGE, PageParams


def page_params(default_per_page: int = DEFAULT_PER_PAGE):
    """Strict dependency factory: ``Depends(page_params(50))`` for a 50-row default."""

    def dependency(
        page: int = Query(1, ge=1),
        per_page: int = Query(default_per_page, ge=1, le=MAX_PER_PAGE),
    ) -> PageParams:
        return PageParams(page=page, per_page=per_page)

    return dependency


def _lenient_int(raw: str | None, fallback: int) -> int:
    try:
        return int(raw) if raw is not None else fallback
    except ValueError:
        return fallback


def lenient_page_params(default_per_page: int = DEFAULT_PER_PAGE):
    """Clamping dependency factory for browser-facing view routes."""

    def dependency(
        page: str | None = Query(None),
        per_page: str | None = Query(None),
    ) -> PageParams:
        return PageParams(
            page=_lenient_int(page, 1), per_page=_lenient_int(per_page, default_per_page)
        )

    return dependency


PageParamsDep = Annotated[PageParams, Depends(page_params())]
LenientPageParamsDep = Annotated[PageParams, Depends(lenient_page_params())]

__all__ = [
    "LenientPageParamsDep",
    "PageParamsDep",
    "lenient_page_params",
    "page_params",
]

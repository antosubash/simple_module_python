"""Fetch every page of a list endpoint, whatever shape it paginates in."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, Literal

from simple_module_remote.generate.operations import Operation

__all__ = ["PaginationStyle", "iter_items", "pagination_style"]

PaginationStyle = Literal["page_envelope", "page_per_page", "file_storage"]

PAGE = "page"
PER_PAGE = "per_page"
DEFAULT_PER_PAGE = 100


def pagination_style(op: Operation, response_schema: dict | None) -> PaginationStyle | None:
    """Which paging shape ``op`` uses, or ``None`` when it does not page by page/per_page."""
    names = {p.name for p in op.params if p.location == "query"}
    if not {PAGE, PER_PAGE} <= names or not response_schema:
        return None
    if response_schema.get("type") == "array":
        return "page_per_page"
    props = response_schema.get("properties") or {}
    if "items" not in props:
        return None
    return "page_envelope" if "pages" in props else "file_storage"


def _items_of(payload: Any, style: PaginationStyle) -> tuple[list[Any], dict]:
    if style == "page_per_page":
        return (payload if isinstance(payload, list) else []), {}
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"], payload
    return [], {}


def _exhausted(
    meta: dict, style: PaginationStyle, page: int, requested: int, count: int
) -> bool | None:
    """Whether this was the last page according to the response metadata; ``None`` if unknown."""
    if style == "page_envelope" and isinstance(meta.get("pages"), int):
        return page >= meta["pages"]
    if style == "file_storage" and isinstance(meta.get("total"), int):
        served = meta.get(PER_PAGE) if isinstance(meta.get(PER_PAGE), int) else requested
        return (page - 1) * served + count >= meta["total"]
    return None


def iter_items(
    fetch: Callable[[dict], Any],
    style: PaginationStyle,
    params: dict,
    limit: int | None,
    on_progress: Callable[[int], None],
) -> Iterator[Any]:
    """Yield items page by page; stop on a short or empty page, the last page, or ``limit``."""
    query = dict(params)
    query.setdefault(PER_PAGE, DEFAULT_PER_PAGE)
    per_page = int(query[PER_PAGE])
    page = int(query.get(PAGE) or 1)
    seen = 0
    while limit is None or seen < limit:
        query[PAGE] = page
        items, meta = _items_of(fetch(dict(query)), style)
        for item in items:
            if limit is not None and seen >= limit:
                return
            seen += 1
            yield item
        on_progress(seen)
        if not items:
            return
        done = _exhausted(meta, style, page, per_page, len(items))
        # The server may clamp per_page, so a short page only ends the walk without metadata.
        if done or (done is None and len(items) < per_page):
            return
        page += 1

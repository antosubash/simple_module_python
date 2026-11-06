"""Link crawl: pages linked from the content of the pages already known.

Menus only reach list pages. Detail and edit pages (``/admin/users/<id>``)
are reached from links in those lists, so after the first pass every link in
``<main>`` is collected and one sample per URL *pattern* is added: ids,
numbers and long tokens collapse to ``:id``, so a 50-row table adds one page,
not 50.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

_ID_SEGMENT = re.compile(
    r"^(\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}|[\w-]{24,})$",
    re.IGNORECASE,
)


def pattern(path: str) -> str:
    """``/admin/users/3f2a…/edit?tab=1`` -> ``/admin/users/:id/edit``."""
    parts = urlsplit(path).path.split("/")
    return "/".join(":id" if _ID_SEGMENT.match(p) else p for p in parts)


def extra_pages(
    known: Iterable[str],
    links_by_page: dict[str, list[str]],
    excluded: list[re.Pattern[str]],
    limit: int,
) -> dict[str, str]:
    """Map each new sample path to the page that links to it (its parent)."""
    known = list(known)
    seen = {pattern(p) for p in known}
    covered = {section(p) for p in known}
    found: dict[str, str] = {}
    # A list page's own rows first (``/admin/users/`` -> ``/admin/users/<id>``):
    # a link into another section (an audit entry pointing at a setting) is a
    # worse sample of that section's pages than the section's own list.
    ordered = sorted(
        ((parent, href) for parent, links in links_by_page.items() for href in links),
        key=lambda item: section(item[0]) != section(item[1]),
    )
    for parent, href in ordered:
        if len(found) >= limit:
            return found
        path = href.split("#", 1)[0]
        key = pattern(path)
        if not path or key in seen or any(rx.search(path) for rx in excluded):
            continue
        # A section the audit already reaches gets its samples from its own
        # pages (next level), not from rows elsewhere that point into it.
        if section(path) != section(parent) and section(path) in covered:
            continue
        seen.add(key)
        found[path] = parent
    return found


def section(path: str, depth: int = 2) -> str:
    """The first *depth* path segments: ``/admin/users/<id>`` -> ``admin/users``."""
    return "/".join(urlsplit(path).path.strip("/").split("/")[:depth])


def hubs_for(path: str, parent: str | None, known: list[str]) -> list[str]:
    """Known pages likely to link to *path*.

    Its parent, then a page of the same area (``/admin/...`` pages share the
    admin sidebar, which the home page does not render), then home.
    """
    area = [p for p in known if p != path and section(p, 1) == section(path, 1)]
    candidates = [parent, *area[:1], "/"]
    out: list[str] = []
    for hub in candidates:
        if hub and hub != path and hub not in out:
            out.append(hub)
    return out

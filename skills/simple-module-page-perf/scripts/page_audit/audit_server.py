"""Server side of the audit: Inertia JSON responses fetched like the client does.

Each page is requested with the same headers ``router.visit`` sends, so the
response is exactly what a client-side navigation costs: the JSON body, the
``Server-Timing`` header a development host adds (app time, SQL statement
count), any redirect, and the deferred/merge/once props the page declares.
"""

from __future__ import annotations

import gzip
import json
import re
import statistics
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import APIRequestContext

_APP_DUR = re.compile(r"\bapp;dur=([\d.]+)")
_DB = re.compile(r'\bdb;dur=([\d.]+);desc="(\d+) quer')
_GZIP_LEVEL = 5  # what the framework's GZipMiddleware uses
_TOP_PROPS = 5
# Shared props every page carries; reported apart from the page's own props.
SHARED_PROPS = ("auth", "menus", "i18n", "errors", "flash", "csrf_token", "branding")


@dataclass(slots=True)
class ServerResult:
    path: str
    status: int = 0
    component: str = ""
    final_url: str = ""
    redirected: bool = False
    wall_ms: float = 0.0
    app_ms: float | None = None
    cold_app_ms: float | None = None
    db_ms: float | None = None
    queries: int | None = None
    json_bytes: int = 0
    gzip_bytes: int = 0
    i18n_bytes: int = 0
    shared_bytes: int = 0
    top_props: list[tuple[str, int]] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    merge: list[str] = field(default_factory=list)
    once: list[str] = field(default_factory=list)
    error: str = ""


def _size(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":"), default=str).encode())


def _timing(header: str | None) -> tuple[float | None, float | None, int | None]:
    if not header:
        return None, None, None
    app = _APP_DUR.search(header)
    db = _DB.search(header)
    return (
        float(app.group(1)) if app else None,
        float(db.group(1)) if db else None,
        int(db.group(2)) if db else None,
    )


def inertia_headers(version: str | None, i18n_key: str | None) -> dict[str, str]:
    """The headers ``@inertiajs/react`` sends on a client-side visit."""
    headers = {
        "X-Inertia": "true",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/html, application/xhtml+xml",
    }
    if version:
        headers["X-Inertia-Version"] = version
    if i18n_key:
        # The tab already holds this catalog, so the server can leave it out.
        headers["X-SM-I18n"] = i18n_key
    return headers


def probe(
    request: APIRequestContext,
    base_url: str,
    path: str,
    headers: dict[str, str],
    rounds: int,
) -> ServerResult:
    """Fetch *path* ``rounds + 1`` times (the first is the cold sample)."""
    result = ServerResult(path=path)
    walls: list[float] = []
    apps: list[float] = []
    dbs: list[float] = []
    queries: list[int] = []
    page: dict[str, Any] | None = None
    for attempt in range(rounds + 1):
        started = time.perf_counter()
        response = request.get(base_url + path, headers=headers)
        elapsed = (time.perf_counter() - started) * 1000
        result.status = response.status
        result.final_url = response.url
        if response.status != 200 or "x-inertia" not in response.headers:
            result.error = f"HTTP {response.status} (not an Inertia page response)"
            return result
        app_ms, db_ms, count = _timing(response.headers.get("server-timing"))
        if attempt == 0:
            result.cold_app_ms = app_ms
            body = response.body()
            page = json.loads(body)
            result.json_bytes = len(body)
            result.gzip_bytes = len(gzip.compress(body, _GZIP_LEVEL))
            continue
        walls.append(elapsed)
        if app_ms is not None:
            apps.append(app_ms)
        if db_ms is not None and count is not None:
            dbs.append(db_ms)
            queries.append(count)
    # Every redirect is one more round trip before anything paints.
    result.redirected = urlsplit(result.final_url).path != urlsplit(path).path
    result.wall_ms = statistics.median(walls) if walls else 0.0
    result.app_ms = statistics.median(apps) if apps else None
    result.db_ms = statistics.median(dbs) if dbs else None
    # The cheapest round is the page's own cost: auth adds statements on its
    # own schedule (loading the principal, the session-version re-check).
    result.queries = min(queries) if queries else None
    if page is not None:
        _describe_page(result, page)
    return result


def _describe_page(result: ServerResult, page: dict[str, Any]) -> None:
    props: dict[str, Any] = page.get("props") or {}
    result.component = str(page.get("component", ""))
    i18n = props.get("i18n") or {}
    result.i18n_bytes = _size(i18n.get("messages")) if i18n.get("messages") else 0
    result.shared_bytes = sum(_size(props[k]) for k in SHARED_PROPS if k in props)
    own = {k: v for k, v in props.items() if k not in SHARED_PROPS}
    sizes = sorted(((k, _size(v)) for k, v in own.items()), key=lambda kv: -kv[1])
    result.top_props = sizes[:_TOP_PROPS]
    deferred = page.get("deferredProps") or {}
    result.deferred = sorted({p for group in deferred.values() for p in group})
    result.merge = sorted(
        set(page.get("mergeProps") or [])
        | set(page.get("prependProps") or [])
        | set(page.get("deepMergeProps") or [])
    )
    result.once = sorted((page.get("onceProps") or {}).keys())


def discover_paths(page_props: dict[str, Any]) -> list[str]:
    """Every root-relative ``url``/``href`` found in the shared ``menus`` prop."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("url", "href") and isinstance(value, str) and value.startswith("/"):
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(page_props.get("menus"))
    return found

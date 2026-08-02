"""Every sidebar link must hit its route directly, with no redirect.

A menu item pointing at ``/catalog`` when the route is registered at
``/catalog/`` still works — Starlette 307s to the canonical path and the
client follows. But it costs a full extra round trip on *every* navigation to
that page. On localhost that's ~8 ms and invisible; on a 40 ms-latency link it
roughly doubles the navigation, and it is worse on mobile.

Five of the eight sidebar links had this mismatch when this test was written.
It is a whole class of bug that no functional test catches, because everything
still renders correctly — just slower.
"""

from __future__ import annotations

import httpx
import pytest
from simple_module_hosting.middleware import InertiaLayoutDataMiddleware

_REDIRECT_CODES = {301, 302, 307, 308}
_NOT_FOUND = 404


def _menu_urls(app) -> list[str]:
    """Every internal menu URL registered by the installed modules."""
    for mw in app.user_middleware:
        if mw.cls is InertiaLayoutDataMiddleware:
            registry = mw.kwargs["menu_registry"]
            break
    else:  # pragma: no cover - the middleware is always installed
        pytest.fail("InertiaLayoutDataMiddleware not installed")

    return sorted(
        {
            item.url
            for item in registry.all_items
            if item.url.startswith("/") and item.method == "get"
        }
    )


async def test_menu_urls_do_not_redirect(app, authenticated_client: httpx.AsyncClient) -> None:
    """No sidebar link may cost a redirect hop."""
    offenders: list[str] = []
    for url in _menu_urls(app):
        resp = await authenticated_client.get(url, headers={"X-Inertia": "true"})
        if resp.status_code in _REDIRECT_CODES:
            offenders.append(f"{url} -> {resp.status_code} {resp.headers.get('location', '')}")

    assert not offenders, (
        "These menu URLs redirect, costing an extra round trip on every "
        "navigation. Point the menu item at the canonical path (usually adding "
        "a trailing slash), or register the route without one:\n  "
        + "\n  ".join(offenders)
    )


async def test_menu_urls_resolve(app, authenticated_client: httpx.AsyncClient) -> None:
    """A menu item pointing at a route that doesn't exist is a dead link."""
    dead: list[str] = []
    for url in _menu_urls(app):
        resp = await authenticated_client.get(url, headers={"X-Inertia": "true"})
        if resp.status_code == _NOT_FOUND:
            dead.append(url)

    assert not dead, f"menu URLs resolve to 404: {dead}"

"""The Inertia error page must carry the same shared props as any other page.

``render_error_page`` builds its own ``Inertia`` instance instead of going
through ``get_inertia``, so it skipped the ``inertia.share(**shared)`` step.
The consequence was visible: a 404 rendered its copy as raw translation keys
— ``host.error.not_found_title``, ``host.error.go_home`` — because the page
received no ``i18n`` block at all. It also lost ``auth`` and ``menus``, so the
error page could not render the layout a signed-in user expects.
"""

from __future__ import annotations

import html
import json
import re

import httpx
import pytest

_NOT_FOUND = 404
_MISSING_PATH = "/definitely/not/a/real/route"


def _inertia_page(body: str) -> dict:
    """Pull the JSON blob Inertia embeds in the server-rendered document."""
    match = re.search(r'data-page="([^"]+)"', body) or re.search(r"data-page='([^']+)'", body)
    if match is None:
        pytest.fail("no data-page attribute found — the error page did not render via Inertia")
    return json.loads(html.unescape(match.group(1)))


class TestErrorPageSharedProps:
    async def test_error_page_renders_via_inertia(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.get(_MISSING_PATH)
        assert resp.status_code == _NOT_FOUND
        assert _inertia_page(resp.text)["component"] == "Error"

    async def test_error_page_carries_i18n_messages(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Without this the page prints raw keys like host.error.not_found_title."""
        resp = await authenticated_client.get(_MISSING_PATH)
        props = _inertia_page(resp.text)["props"]
        assert "i18n" in props, f"error page has no i18n block; props={sorted(props)}"
        assert props["i18n"].get("messages"), "i18n block present but messages are empty"

    async def test_error_page_carries_auth_and_menus(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The layout needs these to render for a signed-in user."""
        props = _inertia_page((await authenticated_client.get(_MISSING_PATH)).text)["props"]
        assert "auth" in props, f"error page has no auth block; props={sorted(props)}"
        assert "menus" in props, f"error page has no menus block; props={sorted(props)}"

    async def test_error_page_keeps_its_own_props(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Sharing must not clobber status/message."""
        props = _inertia_page((await authenticated_client.get(_MISSING_PATH)).text)["props"]
        assert props["status"] == _NOT_FOUND

    async def test_error_page_carries_correlation_id(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The page shows this id so a support report can be joined to the logs."""
        resp = await authenticated_client.get(_MISSING_PATH)
        props = _inertia_page(resp.text)["props"]
        assert props.get("correlation_id"), (
            f"no correlation_id on error page; props={sorted(props)}"
        )
        # Must be the same id the response header advertises, or quoting it
        # back would point support at a different request.
        assert props["correlation_id"] == resp.headers.get("x-correlation-id")

    async def test_anonymous_error_page_still_renders(self, client: httpx.AsyncClient) -> None:
        """An unauthenticated 404 must not blow up on missing shared state."""
        resp = await client.get("/health/definitely-not-real")
        assert resp.status_code >= _NOT_FOUND

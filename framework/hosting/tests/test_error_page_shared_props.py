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
from fastapi import Depends, Request
from simple_module_hosting.permissions import RequiresPermission

_NOT_FOUND = 404
_FORBIDDEN = 403
_MISSING_PATH = "/definitely/not/a/real/route"
_GUARDED_PERMISSION = "settings.manage"
_GUARDED_PATH = "/permission-guard-probe"


def _without_the_guarded_permission(request: Request) -> None:
    """Stand in for a viewer whose roles do not grant the guarded permission.

    The suite's only seeded account is an admin holding the wildcard, so
    ``RequiresPermission`` would wave it straight through. Narrowing the
    resolved set the guard reads is the smallest way to reach its deny branch
    without inventing a second user and a second signed cookie.
    """
    request.state.resolved_permissions = {"settings.view"}


@pytest.fixture
async def guarded_client(app, authenticated_client: httpx.AsyncClient) -> httpx.AsyncClient:
    """``authenticated_client``, plus a route its user is not allowed to open.

    The route is mounted here rather than borrowed from a module: the point is
    the framework guard, and pinning the test to whichever module happens to
    ship a ``settings.manage`` endpoint today would make it fail for reasons
    that have nothing to do with error pages.
    """

    async def _probe() -> dict[str, bool]:
        return {"ok": True}

    app.add_api_route(
        _GUARDED_PATH,
        _probe,
        methods=["GET"],
        dependencies=[
            Depends(_without_the_guarded_permission),
            Depends(RequiresPermission(_GUARDED_PERMISSION)),
        ],
    )
    return authenticated_client


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


class TestRequiredPermissionProp:
    """A 403 from ``RequiresPermission`` must name the permission on the page.

    The page's 403 copy is "Your role doesn't include ``<perm>``. Ask an admin
    to grant it." — it can only say that if the missing permission reaches it
    as its own prop. The guard already puts the name in the exception detail
    ("Permission required: settings.manage"), but that string is a *message*
    for a human, and rendering it verbatim would leak the wording of a Python
    exception into the UI. Parsing it back out here keeps one source of truth
    for the permission name and lets the page own the sentence.
    """

    async def test_permission_denied_page_names_the_permission(
        self, guarded_client: httpx.AsyncClient
    ) -> None:
        resp = await guarded_client.get(_GUARDED_PATH)
        assert resp.status_code == _FORBIDDEN
        props = _inertia_page(resp.text)["props"]
        assert props.get("required_permission") == _GUARDED_PERMISSION, (
            f"403 page did not carry the missing permission; props={sorted(props)}"
        )

    async def test_a_written_detail_still_reaches_the_page(
        self, guarded_client: httpx.AsyncClient
    ) -> None:
        """Only the boilerplate is dropped — a sentence a caller wrote survives."""
        props = _inertia_page((await guarded_client.get(_GUARDED_PATH)).text)["props"]
        assert props["message"] == f"Permission required: {_GUARDED_PERMISSION}"

    async def test_other_errors_carry_no_permission(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """A 404 has no permission to name — the prop must be present and null,
        not absent, or the page cannot tell "no permission involved" from "prop
        was never wired"."""
        props = _inertia_page((await authenticated_client.get(_MISSING_PATH)).text)["props"]
        assert "required_permission" in props, f"prop missing entirely; props={sorted(props)}"
        assert props["required_permission"] is None


class TestStatusPhraseIsNotAMessage:
    """The default ``HTTPException.detail`` is the status name, not copy.

    Starlette fills ``detail`` with ``HTTPStatus(code).phrase`` when a caller
    gives none, so a plain ``HTTPException(404)`` arrives at the page carrying
    "Not Found" and a bare ``HTTPException(403)`` carrying "Forbidden". The
    page prefers a server message over its own catalog description — correct
    when the message says something ("Administrator access required"), useless
    when it restates the title. Left alone, the deck's 404 and 403 sentences
    would be unreachable on the paths that actually produce them.
    """

    async def test_unmatched_url_sends_no_message(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        props = _inertia_page((await authenticated_client.get(_MISSING_PATH)).text)["props"]
        assert not props["message"], (
            "the status phrase reached the page as a message, so it renders in "
            f"place of the catalog description: {props['message']!r}"
        )

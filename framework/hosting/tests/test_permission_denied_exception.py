"""The 403 page names the missing permission from the exception, not its text."""

from __future__ import annotations

import html
import json
import re

import httpx
from fastapi import HTTPException
from simple_module_core.permission_denied import PermissionDenied

_PATH = "/permission-denied-probe"


def _props(body: str) -> dict:
    match = re.search(
        r'<script data-page="[^"]*" type="application/json">(.*?)</script>', body, re.DOTALL
    ) or re.search(r"data-page='([^']+)'", body)
    assert match is not None, "error page did not render via Inertia"
    return json.loads(html.unescape(match.group(1)))["props"]


async def test_page_names_permission_even_when_message_is_reworded(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    async def _probe() -> None:
        raise PermissionDenied("reports.export", "Vous n'avez pas le droit")

    app.add_api_route(_PATH, _probe, methods=["GET"])
    resp = await authenticated_client.get(_PATH)
    assert resp.status_code == 403
    props = _props(resp.text)
    assert props["required_permission"] == "reports.export"
    assert props["message"] == "Vous n'avez pas le droit"

    api = await authenticated_client.get(_PATH, headers={"Accept": "application/json"})
    assert api.status_code == 403
    assert api.json() == {"detail": "Vous n'avez pas le droit"}


async def test_message_that_merely_looks_like_the_old_prefix_names_nothing(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    async def _probe() -> None:
        raise HTTPException(403, "Permission required: sneaky.perm")

    app.add_api_route(_PATH + "-plain", _probe, methods=["GET"])
    resp = await authenticated_client.get(_PATH + "-plain")
    assert _props(resp.text)["required_permission"] is None

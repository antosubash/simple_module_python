"""The host supplies a ``homeUrl`` default when no module does (#427).

The users module publishes its configured landing URL; an install without it
(Keycloak) must still point the layouts' home links at the Dashboard rather
than falling back to ``/``.
"""

from __future__ import annotations

from types import SimpleNamespace

from simple_module_hosting._inertia_shared import default_home_url


def _app(prefixes: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(view_prefixes=prefixes)))


def test_dashboard_installed_is_home() -> None:
    assert default_home_url(_app({"Users": "/users", "Dashboard": "/dashboard"})) == "/dashboard/"


def test_without_dashboard_home_is_root() -> None:
    assert default_home_url(_app({"Admin": "/admin/things"})) == "/"


def test_no_services_yet_home_is_root() -> None:
    assert default_home_url(SimpleNamespace(state=SimpleNamespace())) == "/"


async def test_page_payload_carries_home_url(authenticated_client) -> None:
    # In the full app the users module's own value wins; either way the key is
    # always present, so the client fallback is a last resort only.
    resp = await authenticated_client.get("/admin/", headers={"X-Inertia": "true"})
    assert resp.json()["props"]["homeUrl"].endswith("/")

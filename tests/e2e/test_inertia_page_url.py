"""E2E guard for the Inertia page url being root-relative.

``fastapi-inertia`` builds the page object with ``"url": str(request.url)`` —
absolute. Behind a TLS-terminating reverse proxy the container sees ``http``
while the browser is on ``https``, so the client hands ``history.pushState`` a
cross-origin url and the browser refuses it with a ``SecurityError`` on every
single page. History state is then never written, so back/forward navigation
and scroll restoration silently stop working (GH #223).

Unit tests pin the rewrite itself. This pins the consequence in a real browser:
that the payload the client actually receives carries no origin, that the state
write lands, and that a client-side visit — the only path that calls
``pushState`` rather than ``replaceState`` — survives it.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

#: Routes that render an Inertia page and are reachable as an admin. The 404 is
#: deliberate: ``render_error_page`` builds its own Inertia instance, so it was
#: the one page still throwing after every other had been fixed.
_ROUTES = [
    "/",
    "/users/login",
    "/dashboard/",
    "/admin",
    "/admin/users/",
    "/admin/settings/",
    "/file-storage/",
    "/definitely-not-a-real-route",
]


def _login(page: Page, username: str, password: str) -> None:
    page.goto("/users/login")
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/dashboard/**", timeout=15_000)


def _page_payload_url(page: Page) -> str | None:
    """The ``url`` the server put in the ``data-page`` blob, or None."""
    raw = page.evaluate(
        "() => { const el = document.getElementById('app'); return el ? el.dataset.page : null; }"
    )
    if not raw:
        return None
    return json.loads(raw).get("url")


@pytest.mark.parametrize("route", _ROUTES)
def test_page_url_is_root_relative(
    page: Page, e2e_username: str, e2e_password: str, route: str
) -> None:
    """No origin may appear in the payload — that is what breaks pushState."""
    _login(page, e2e_username, e2e_password)
    page.goto(route)
    url = _page_payload_url(page)
    assert url is not None, f"{route} rendered no Inertia payload"
    assert not url.startswith(("http://", "https://")), (
        f"{route} shipped an absolute page url ({url!r}); behind a TLS proxy "
        "this makes every history write throw a SecurityError"
    )
    assert url.startswith("/"), f"{route} page url is not root-relative: {url!r}"


def test_no_history_security_error_on_any_route(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """The console must stay free of the pushState SecurityError."""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on(
        "console",
        lambda msg: errors.append(msg.text) if msg.type == "error" else None,
    )

    _login(page, e2e_username, e2e_password)
    for route in _ROUTES:
        page.goto(route)

    history_errors = [e for e in errors if "pushState" in e or "replaceState" in e]
    assert not history_errors, f"history write was rejected: {history_errors}"


def test_history_state_is_written_and_back_works(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """A client-side visit is the real pushState path; a load only replaces.

    A rejected state write leaves ``history.state`` null and makes the back
    button a no-op — the user-visible half of GH #223, which no amount of
    console-watching would catch on its own.
    """
    _login(page, e2e_username, e2e_password)
    page.goto("/dashboard/")
    assert page.evaluate("() => window.history.state !== null"), (
        "the initial replaceState did not land"
    )

    page.get_by_role("link", name="Files").first.click()
    page.wait_for_url("**/file-storage/**", timeout=15_000)
    assert page.evaluate("() => window.history.state !== null"), (
        "the client-side visit's pushState did not land"
    )

    page.go_back()
    page.wait_for_url("**/dashboard/**", timeout=15_000)
    expect(page.locator("#app")).to_be_attached()


def test_a_default_favicon_is_served(page: Page) -> None:
    """Without one the browser falls back to /favicon.ico, which this app
    does not route — a console error on every full page load."""
    page.goto("/")
    href = page.evaluate(
        "() => { const l = document.querySelector('link[rel=\"icon\"]');"
        " return l ? l.getAttribute('href') : null; }"
    )
    assert href, "no <link rel=icon> was rendered"
    decoded = page.evaluate(
        "(href) => new Promise(res => { const i = new Image();"
        " i.onload = () => res(i.naturalWidth > 0);"
        " i.onerror = () => res(false); i.src = href; })",
        href,
    )
    assert decoded, f"the favicon did not decode as an image: {href[:60]!r}"

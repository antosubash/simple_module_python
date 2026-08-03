"""Every asset a page requests must actually resolve.

Guards a bug that no other check caught. Vite records a lazy chunk's preload
dependencies as base-relative paths (``"assets/Browse-x.js"``) and prefixes
them with ``base`` at runtime. With the default ``base: "/"`` those requests
went to ``/assets/...`` while the host serves the build under
``/static/dist/`` — so every lazy page load fired requests the SPA fallback
answered with HTML, producing a 404 plus a MIME-type console error.

The app still worked, because the *actual* dynamic import uses a relative
``"./"`` specifier and resolved correctly; only the preloads were wasted. That
is exactly why nothing caught it: no test failed, no page broke, the network
tab just quietly filled with errors on every navigation.

Run against a PRODUCTION build — the bug cannot reproduce in dev, where Vite
serves modules from its own origin.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = [pytest.mark.perf, pytest.mark.e2e]

ROUTES = ("/users/login", "/dashboard/", "/audit_log/", "/users/admin")
_SETTLE_MS = 1500
_CLIENT_ERROR = 400
# Chrome reports a module served as text/html this way; it is the signature of
# an asset URL falling through to the SPA fallback.
_MIME_ERROR_MARKER = "MIME type"


def test_no_failed_requests_across_key_routes(
    logged_in_page: Page, base_url: str, perf_build: str
) -> None:
    """No 4xx/5xx for any subresource on any main route."""
    page = logged_in_page
    bad: list[str] = []
    page.on(
        "response",
        lambda r: (
            bad.append(f"{r.status} {r.url.replace(base_url, '')}")
            if r.status >= _CLIENT_ERROR
            else None
        ),
    )

    for route in ROUTES:
        page.goto(f"{base_url}{route}", wait_until="load")
        page.wait_for_timeout(_SETTLE_MS)

    assert not bad, (
        f"({perf_build}) requests failed while loading {list(ROUTES)}:\n  "
        + "\n  ".join(sorted(set(bad)))
        + "\n\nIf these are /assets/... without the /static/dist/ prefix, `base` "
        "is wrong in host/client_app/vite.config.ts."
    )


def test_no_console_errors_across_key_routes(
    logged_in_page: Page, base_url: str, perf_build: str
) -> None:
    """A clean console. Catches MIME-type failures from misrouted modules."""
    page = logged_in_page
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text[:200]) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"uncaught: {e}"[:200]))

    for route in ROUTES:
        page.goto(f"{base_url}{route}", wait_until="load")
        page.wait_for_timeout(_SETTLE_MS)

    mime = [e for e in errors if _MIME_ERROR_MARKER in e]
    assert not mime, (
        f"({perf_build}) modules were served as HTML — an asset URL is falling "
        f"through to the SPA fallback:\n  " + "\n  ".join(sorted(set(mime)))
    )
    assert not errors, f"({perf_build}) console errors:\n  " + "\n  ".join(sorted(set(errors)))


def test_lazy_page_chunks_resolve_under_the_static_prefix(
    logged_in_page: Page, base_url: str
) -> None:
    """Every JS request must sit under /static/dist/.

    Asserts the *shape* of the URL rather than just the status code, so this
    still fails if a future SPA fallback starts returning 200 for unknown
    asset paths and hides the 404s.
    """
    page = logged_in_page
    js_urls: list[str] = []
    page.on(
        "response",
        lambda r: (
            js_urls.append(r.url.replace(base_url, ""))
            if r.request.resource_type == "script"
            else None
        ),
    )

    # A route whose page component is a lazily-imported chunk.
    page.goto(f"{base_url}/audit_log/", wait_until="load")
    page.wait_for_timeout(_SETTLE_MS)

    stray = [u for u in js_urls if u.startswith("/assets/")]
    assert not stray, "script requests bypassed the /static/dist/ prefix:\n  " + "\n  ".join(
        sorted(set(stray))
    )
    assert js_urls, "no script requests captured — selector or build is broken"

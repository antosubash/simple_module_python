"""Capture the Keycloak redirect interstitial, which never paints on its own.

``Keycloak/Login`` calls ``window.location.assign('/api/keycloak/auth/login')``
from a mount effect, so a plain ``page.goto`` leaves the browser on whatever the
realm redirect lands on and screenshots that instead. The committed evidence for
deck screen 07 was byte-identical to ``07-keycloak-loggedout`` for exactly this
reason — two files claiming to show different screens, both showing the second.

Answering that one request with a 204 holds the page on the interstitial
without changing the component: browsers stay put on a navigation that returns
No Content. What is captured is what a user sees while the redirect is in
flight, or permanently if the realm is unreachable.

Not ``route.abort()``: this is a *top-level* navigation, so aborting it lands
the browser on ``chrome-error://chromewebdata/`` and screenshots a blank error
page — a second way to produce evidence of the wrong screen.

The screen only exists when Keycloak is the *active* auth provider — with
``users`` active, ``AuthMiddleware`` 302s ``/keycloak/login`` to ``/users/login``
— so the server this points at must be booted with::

    SM_AUTH_PROVIDER=keycloak
    SM_KEYCLOAK_SERVER_URL=https://sso.example.com
    SM_KEYCLOAK_REALM=acme
    SM_KEYCLOAK_CLIENT_ID=simple-module

Usage::

    uv run python scripts/shoot_keycloak_interstitial.py \
        --base http://localhost:8123 --out qa-shots/hifi
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWPORTS = {"desktop": (1440, 900), "phone": (390, 720)}
START_LOGIN_URL = "**/api/keycloak/auth/login"
SCREEN = "07-keycloak-login"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8123")
    ap.add_argument("--out", default="qa-shots/hifi")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        # Hold the page: answer the redirect the mount effect fires with a
        # 204, which a browser declines to navigate to.
        page.route(START_LOGIN_URL, lambda route: route.fulfill(status=204, body=""))

        for viewport, (width, height) in VIEWPORTS.items():
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{args.base}/keycloak/login", wait_until="networkidle")
            # The heading is the proof we are on the interstitial and not on
            # whatever the redirect would otherwise have reached.
            page.wait_for_selector("text=Redirecting", timeout=10_000)
            page.wait_for_timeout(400)
            target = out / f"{SCREEN}-{viewport}.png"
            page.screenshot(path=str(target), full_page=True)
            print(f"{SCREEN:26s} {viewport:8s} {page.url} -> {target}")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

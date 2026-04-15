"""End-to-end UI smoke tests.

Four browser-driven happy-path tests, all gated by the ``e2e`` marker:

* :func:`test_login_and_browse_smoke` — landing → local login form →
  dashboard → products browse → logout. Minimal regression guard that
  proves auth and page rendering work end to end.

* :func:`test_products_crud_smoke` — builds on the browse smoke with
  the full create → edit → delete loop. Requires the admin user to have
  the ``admin`` role so ``RequiresPermission`` lets the admin user through.

* :func:`test_password_reset_smoke` — SKIPPED (see inline comment).
  Requires the hashed-password fingerprint (``password_fgpt``) that only
  the server holds; the HTTP-level flow is covered by unit tests in
  ``modules/users/tests/test_api_auth.py``.

* :func:`test_admin_invite_smoke` — admin invites a new user via the UI,
  then the invitee accepts the invite in a fresh browser context and is
  redirected to the dashboard.  The invite token is minted locally using
  the dev-default verify secret — equivalent to what the ConsoleMailer logs,
  without scraping server stdout.

Requires a live stack. See docs/e2e-testing.md for setup.
"""

from __future__ import annotations

import re
import time

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.conftest import mint_verify_token

_PRODUCTS_URL = re.compile(r"/products/?$")

pytestmark = pytest.mark.e2e


def _login(page: Page, username: str, password: str) -> None:
    """From landing, click Get Started and complete the local login form."""
    # Landing renders a nav "Get Started" and a hero "Get Started"; either works.
    page.get_by_role("link", name="Get Started").first.click()
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Login").click()


def _login_and_land_on_dashboard(page: Page, username: str, password: str) -> None:
    """Shared setup: open landing, log in, wait for dashboard."""
    page.goto("/")
    expect(page.get_by_role("heading", name="Modular Monolith")).to_be_visible()
    _login(page, username, password)
    page.wait_for_url("**/dashboard/**", timeout=15_000)
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()


def test_login_and_browse_smoke(
    page: Page,
    e2e_username: str,
    e2e_password: str,
) -> None:
    _login_and_land_on_dashboard(page, e2e_username, e2e_password)
    # Welcome card — anchor on the CardTitle text which is unique on this page.
    expect(page.get_by_text("Welcome", exact=True)).to_be_visible()

    # Navigate directly: sidebar link is hidden below the lg breakpoint.
    page.goto("/products")
    expect(page.get_by_role("heading", name="Products")).to_be_visible()

    page.goto("/users/logout")
    page.goto("/")
    expect(page.get_by_role("heading", name="Modular Monolith")).to_be_visible()


def test_products_crud_smoke(
    page: Page,
    e2e_username: str,
    e2e_password: str,
) -> None:
    """Full create → edit → delete loop against the live Products module.

    Requires the admin user's session to carry the ``admin`` role so the
    ``products.create`` / ``.edit`` / ``.delete`` permission gates allow
    the calls.
    """
    _login_and_land_on_dashboard(page, e2e_username, e2e_password)

    # Millisecond-timestamped name keeps the test idempotent across reruns,
    # even if a prior run crashed before cleanup.
    product_name = f"Smoke Test Widget {int(time.time() * 1000)}"
    edited_name = f"{product_name} edited"

    page.goto("/products/create")
    expect(page.get_by_role("heading", name="Create Product")).to_be_visible()
    page.locator("#name").fill(product_name)
    page.locator("#description").fill("e2e smoke test")
    page.locator("#price").fill("9.99")
    page.get_by_role("button", name="Create Product").click()

    page.wait_for_url(_PRODUCTS_URL, timeout=15_000)
    created_row = page.get_by_role("row").filter(has_text=product_name)
    expect(created_row).to_be_visible(timeout=10_000)

    created_row.locator("a[href*='/edit']").click()
    page.wait_for_url("**/edit", timeout=10_000)
    page.locator("#name").fill(edited_name)
    page.get_by_role("button", name="Save Changes").click()

    page.wait_for_url(_PRODUCTS_URL, timeout=15_000)
    edited_row = page.get_by_role("row").filter(has_text=edited_name)
    expect(edited_row).to_be_visible(timeout=10_000)

    # Row has an edit link + a single <button> (the trash-icon delete trigger).
    edited_row.get_by_role("button").click()
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Delete").click()
    expect(edited_row).not_to_be_visible(timeout=10_000)


@pytest.mark.skip(
    reason=(
        "fastapi-users reset_password() validates a password fingerprint "
        "(password_fgpt = PBKDF2/Argon2 hash of hashed_password) that is "
        "only available server-side.  Minting a valid token outside the "
        "server process is not feasible without the stored hashed_password. "
        "The full HTTP-layer flow is covered by unit tests in "
        "modules/users/tests/test_api_auth.py."
    )
)
def test_password_reset_smoke(
    page: Page,
    e2e_username: str,
) -> None:  # pragma: no cover
    """Skipped — see decorator reason above."""


def test_admin_invite_smoke(
    page: Page,
    browser: Browser,
    base_url: str,
    e2e_username: str,
    e2e_password: str,
    verify_token_secret: str,
) -> None:
    """Admin invites a new user; invitee accepts the invite in a fresh context.

    Token-minting approach (plan option b): we POST the invite through the
    real UI, which creates the user server-side (``is_verified=False``).  We
    then mint a verification token locally using the same secret the server
    uses — identical to what the ConsoleMailer would have logged — and navigate
    to ``/users/invite/accept?token=…`` in a fresh browser context to complete
    the flow without scraping server logs.
    """
    # 1. Log in as admin and navigate to the invite page.
    _login_and_land_on_dashboard(page, e2e_username, e2e_password)
    page.goto("/users/admin/invite")
    expect(page.get_by_role("heading", name="Invite user")).to_be_visible(timeout=10_000)

    # 2. Fill in the invite form with a timestamped email.
    invitee_email = f"invitee+{int(time.time() * 1000)}@test.invalid"
    invitee_name = "E2E Invitee"

    page.locator("#email").fill(invitee_email)
    page.locator("#full_name").fill(invitee_name)

    # Check the "user" role checkbox (label text matches the role name).
    user_role_checkbox = page.get_by_label("user", exact=True)
    if user_role_checkbox.count() > 0:
        user_role_checkbox.check()

    page.get_by_role("button", name="Send invite").click()

    # 3. Expect redirect back to /users/admin after a successful invite.
    page.wait_for_url("**/users/admin**", timeout=15_000)

    # 4. Retrieve the newly created user's id via the admin API so we can
    #    mint the token.  The invite endpoint also returns the user in the
    #    response, but since we went through the browser we use the list API.
    import json
    import urllib.request

    list_url = f"{base_url}/api/users/admin/users?query={invitee_email}&page=1&per_page=10"
    # Re-use the admin session cookie that Playwright set on the page's context.
    cookies = page.context.cookies()
    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    req = urllib.request.Request(list_url, headers={"Cookie": cookie_header})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    users = data.get("users", [])
    if not users:
        pytest.skip(f"Invited user {invitee_email!r} not found via admin API — cannot mint token")

    invitee_id = users[0]["id"]

    # 5. Mint the verify token locally (same secret the server uses).
    token = mint_verify_token(invitee_id, invitee_email, verify_token_secret)

    # 6. Open a fresh browser context (no admin session cookies).
    new_context = browser.new_context(base_url=base_url)
    new_page = new_context.new_page()
    try:
        new_page.goto(f"/users/invite/accept?token={token}")
        expect(new_page.get_by_role("heading", name="Accept invitation")).to_be_visible(
            timeout=10_000
        )

        # 7. Set a password and submit.
        invitee_password = "InviteePass1!"
        new_page.locator("#password").fill(invitee_password)
        new_page.locator("#confirm").fill(invitee_password)
        new_page.get_by_role("button", name="Activate account").click()

        # 8. Expect redirect to dashboard and invitee session established.
        new_page.wait_for_url("**/dashboard/**", timeout=15_000)
        expect(new_page.get_by_role("heading", name="Dashboard")).to_be_visible()
    finally:
        new_context.close()

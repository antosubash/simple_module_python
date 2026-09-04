"""The three flows on this branch that change state, driven end to end.

Every other e2e test on the branch reads a page. These three write: a sign-in
that asks for a longer window, a bulk delete, and a download. Each broke at
least once during the branch in a way no unit test saw — the session cookie's
Max-Age is rewritten by middleware after the response is built, the delete is a
fetch whose result the page folds back into its own props, and the export is an
``<a download>`` whose href is assembled from the current filters.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from playwright.sync_api import BrowserContext, Page, expect

pytestmark = pytest.mark.e2e

_REMEMBER_DAYS = 30
_DEFAULT_DAYS = 14
_TOTAL = re.compile(r"howing \d+\D\d+ of ([\d,]+)")


def _login(page: Page, username: str, password: str, *, remember: bool = False) -> None:
    page.goto("/users/login")
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    if remember:
        page.locator("#remember").check()
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/dashboard/**", timeout=15_000)


def _cookie_days(context: BrowserContext) -> float:
    """Days from now until the session cookie expires."""
    cookie = next(c for c in context.cookies() if c["name"] == "session")
    assert cookie["expires"] > 0, "the session cookie was written without an expiry"
    return (cookie["expires"] - time.time()) / 86_400


def test_keep_me_signed_in_writes_a_thirty_day_cookie(
    page: Page, context: BrowserContext, e2e_username: str, e2e_password: str
) -> None:
    """The checkbox is only honest if the cookie outlives the promise.

    Both ends are pinned in one test: without the plain sign-in the assertion
    passes against a build that hands everyone thirty days, and without a
    second page load it passes against one that records the window on the
    sign-in response only — which the session middleware then rolls back to the
    default on the next response that re-emits the cookie.
    """
    _login(page, e2e_username, e2e_password)
    plain = _cookie_days(context)
    assert _DEFAULT_DAYS - 1 < plain <= _DEFAULT_DAYS + 0.1, plain

    context.clear_cookies()
    _login(page, e2e_username, e2e_password, remember=True)
    remembered = _cookie_days(context)
    assert _REMEMBER_DAYS - 1 < remembered <= _REMEMBER_DAYS + 0.1, remembered

    page.goto("/admin/")
    still = _cookie_days(context)
    assert _REMEMBER_DAYS - 1 < still <= _REMEMBER_DAYS + 0.1, still


def _footer_total(page: Page) -> int:
    """The ``… of N`` the table foot is currently showing."""
    match = _TOTAL.search(page.locator("body").inner_text())
    assert match is not None, "the file table foot did not render a range"
    return int(match.group(1).replace(",", ""))


def test_deleting_selected_files_removes_them_and_drops_the_count(
    page: Page, tmp_path, e2e_username: str, e2e_password: str
) -> None:
    """Self-contained: it uploads the two files it then deletes."""
    _login(page, e2e_username, e2e_password)
    page.goto("/file-storage/")
    expect(page.get_by_role("heading", name="File storage")).to_be_visible()

    suffix = str(int(time.time() * 1000))
    names = [f"e2e-delete-a-{suffix}.txt", f"e2e-delete-b-{suffix}.txt"]
    paths = []
    for name in names:
        path = tmp_path / name
        path.write_text(f"e2e fixture {name}\n")
        paths.append(str(path))

    page.locator("input[type=file]").first.set_input_files(paths)
    for name in names:
        expect(page.get_by_role("checkbox", name=f"Select {name}")).to_be_visible(timeout=30_000)

    before = _footer_total(page)

    for name in names:
        page.get_by_role("checkbox", name=f"Select {name}").check()
    page.get_by_role("button", name="Delete selected").click()
    page.get_by_role("button", name="Delete files").click()

    for name in names:
        expect(page.get_by_role("checkbox", name=f"Select {name}")).to_have_count(0, timeout=30_000)
    assert _footer_total(page) == before - 2


def test_the_audit_log_export_downloads_a_csv_with_a_header_row(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    _login(page, e2e_username, e2e_password)
    page.goto("/admin/audit-log/")
    expect(page.get_by_role("heading", name="Audit log")).to_be_visible()

    with page.expect_download(timeout=30_000) as download_info:
        page.get_by_role("link", name="Export CSV").click()
    download = download_info.value

    with Path(download.path()).open(encoding="utf-8") as handle:
        first_line = handle.readline().rstrip("\r\n")

    assert first_line == "time,action,entity_type,entity_id,entity_label,actor,changes"

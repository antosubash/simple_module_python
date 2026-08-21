"""E2E regression test: translated strings resolve on every admin page.

The failure mode this guards against is an i18next upgrade (or a locale-file
rename) silently breaking key resolution, so pages render the *key* instead of
the translation — ``users.browse.title`` where "Users" should be.

That degrades every page at once but breaks no assertion in the other suites:
they locate elements by role and accessible name, and a raw key is still a
perfectly visible heading. Only a check that reads the rendered text catches it.

Added alongside the i18next 23 -> 26 upgrade, which had no automated coverage.

Detection strategy
------------------
Matching a "looks like a dotted key" shape is not good enough: the Settings and
Feature Flags pages legitimately *display* dotted identifiers as data (setting
keys like ``branding.app_name``, flag names like ``file_storage.public_uploads``),
and a shape-based check flags those as leaks.

So instead of guessing, we compare the rendered text against the actual
translation catalogue that the server shipped for this page — ``props.i18n.messages``
on the Inertia page object. A token only counts as leaked if it is genuinely a key
in that catalogue, which means i18next was asked to translate it and handed back
the key. Domain identifiers that merely look similar are absent from the catalogue
and correctly ignored.
"""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e

# i18next here is configured with single-brace delimiters (prefix "{", suffix "}"),
# so an unsubstituted variable surfaces as a literal ``{count}`` in the output.
_RAW_PLACEHOLDER = re.compile(r"\{[a-z_][a-z0-9_]*\}", re.I)

# Any dotted lowercase token — the candidate set we then filter against the catalogue.
_DOTTED_TOKEN = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+\b")

# (label, path) for every page reachable from the sidebar.
_PAGES = [
    ("Dashboard", "/dashboard/"),
    ("Files", "/file-storage/"),
    ("Users", "/admin/users/"),
    ("Feature Flags", "/admin/feature-flags/"),
    ("Branding", "/admin/branding/"),
    ("Background Tasks", "/admin/background-tasks/"),
    ("Settings", "/admin/settings/"),
    ("Audit Log", "/admin/audit-log/"),
]


def _login(page: Page, username: str, password: str) -> None:
    page.get_by_role("link", name="Log in").first.click()
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/dashboard/**", timeout=15_000)


def _translation_keys(page: Page) -> set[str]:
    """Keys from the catalogue the server shipped with this page load.

    Full page loads always carry the complete ``messages`` dict (Inertia XHR
    partials send ``None`` and reuse the client cache, but this test always
    does a full ``goto``).
    """
    raw = page.evaluate("() => document.getElementById('app')?.dataset.page ?? ''")
    if not raw:
        return set()
    messages = json.loads(raw).get("props", {}).get("i18n", {}).get("messages") or {}
    return set(messages)


@pytest.mark.parametrize(("label", "path"), _PAGES, ids=[p[1] for p in _PAGES])
def test_page_renders_no_raw_i18n_keys(
    page: Page, e2e_username: str, e2e_password: str, label: str, path: str
) -> None:
    """Every sidebar page renders resolved translations, not raw keys."""
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    page.goto(path)
    page.wait_for_load_state("networkidle")

    body = page.locator("body").inner_text()
    assert body.strip(), f"{label} ({path}) rendered an empty body"

    catalogue = _translation_keys(page)
    assert catalogue, (
        f"{label} ({path}) shipped an empty i18n catalogue — the check below "
        "would silently pass. Verify InertiaLayoutDataMiddleware is wired up."
    )

    leaked = sorted(set(_DOTTED_TOKEN.findall(body)) & catalogue)
    assert not leaked, (
        f"{label} ({path}) rendered untranslated i18n keys: {leaked}. "
        "These are real keys in the page's own catalogue, so i18next returned "
        "the key instead of its translation — check the i18next configuration "
        "in packages/i18n and the module's locale_dirs()."
    )

    leaked_placeholders = sorted(set(_RAW_PLACEHOLDER.findall(body)))
    assert not leaked_placeholders, (
        f"{label} ({path}) rendered unsubstituted interpolation placeholders: "
        f"{leaked_placeholders}. i18next is configured with single-brace "
        "delimiters; a mismatch here leaves the variable literal in the output."
    )


def test_dashboard_translated_immediately_after_login(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """The catalogue must be live on the page login lands on, with no reload.

    The parametrised test above cannot catch this: it does ``page.goto(path)``
    after logging in, and a full page load re-bootstraps i18n from scratch —
    the path that always worked. The broken path is the client-side Inertia
    navigation login performs, where the *audience* changes while the locale
    does not.

    Anonymous visitors get a public catalogue with admin-only modules withheld.
    Signing in ships the fuller one, but the client dropped it (it only adopted
    a catalogue when the *locale* changed), and even once adopted, react-i18next
    re-rendered nothing because it binds to no resource-store events by default.
    Net effect: every admin screen showed raw keys — "dashboard.home.title" as
    the page heading — until the user happened to hard-refresh.

    So: log in, then assert on whatever the app navigated to, touching nothing.
    """
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    # No goto() here — that is the whole point.
    page.wait_for_load_state("networkidle")

    heading = page.get_by_role("heading", level=1).first.inner_text()
    assert heading.strip(), "dashboard rendered no h1 after login"
    assert "." not in heading, (
        f"dashboard heading rendered a raw i18n key after login: {heading!r}. "
        "The catalogue that arrived with the post-login navigation was not "
        "applied — see packages/i18n (react.bindI18nStore) and "
        "host/client_app/i18n.ts (adopt any non-null messages payload)."
    )

    body = page.locator("body").inner_text()
    catalogue = _translation_keys(page)
    if catalogue:
        leaked = sorted(set(_DOTTED_TOKEN.findall(body)) & catalogue)
        assert not leaked, f"dashboard rendered untranslated keys immediately after login: {leaked}"

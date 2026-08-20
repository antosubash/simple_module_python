"""E2E smoke test for the Audit Log admin UI.

Drives a real browser to /audit_log, verifies the page renders with data
captured by the framework's audit listener, and confirms a freshly-created
Setting produces an audit entry with a resolved (non-empty) entity_id —
the regression test for the two-phase capture fix.
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _login(page: Page, username: str, password: str) -> None:
    page.get_by_role("link", name="Log in").first.click()
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/dashboard/**", timeout=15_000)


def test_audit_log_renders_with_data(page: Page, e2e_username: str, e2e_password: str) -> None:
    """The Audit Log page renders the filter bar, table headers, and at
    least one audit entry (login itself produces a User update entry).
    """
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    page.goto("/audit_log")

    expect(page.get_by_role("heading", name="Audit Log")).to_be_visible()

    expect(page.get_by_role("columnheader", name="Timestamp")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Action")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Entity")).to_be_visible()

    expect(page.get_by_role("button", name="Apply")).to_be_visible()
    expect(page.get_by_role("button", name="Clear")).to_be_visible()

    rows = page.get_by_role("row")
    expect(rows).not_to_have_count(1)


def test_audit_log_captures_integer_pk_setting(
    page: Page, e2e_username: str, e2e_password: str, base_url: str
) -> None:
    """Regression for BUG-002: creating a Setting (integer PK) produces an
    audit entry with a resolved entity_id, not an empty string.
    """
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    suffix = str(int(time.time() * 1000))
    setting_key = f"e2e.audit.intpk.{suffix}"

    create_resp = page.request.post(
        f"{base_url}/api/settings/",
        data={
            "scope": "system",
            "scope_id": "",
            "key": setting_key,
            "value": "x",
            "value_type": "string",
        },
    )
    assert create_resp.ok, f"Setting create failed: {create_resp.status}"
    setting_id = str(create_resp.json()["id"])
    assert setting_id and setting_id != "", "Setting must have a non-empty id"

    audit_resp = page.request.get(
        f"{base_url}/api/audit_log/",
        params={"entity_type": "Setting", "action": "created"},
    )
    assert audit_resp.ok, f"Audit API failed: {audit_resp.status}"
    items = audit_resp.json()["items"]

    # SQLite reuses a deleted row's integer id within a run, so another test's
    # created-then-deleted setting can leave an older audit entry carrying this
    # same id — the guarded regression is only that the id resolved non-empty,
    # so require at least one match rather than exactly one.
    matching = [e for e in items if e["entity_id"] == setting_id]
    assert matching, (
        f"Expected an audit entry with entity_id={setting_id}, "
        f"got entity_ids={[e['entity_id'] for e in items[:5]]}"
    )


def test_audit_log_filter_by_entity_type(page: Page, e2e_username: str, e2e_password: str) -> None:
    """Selecting an entity type in the filter narrows the table."""
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    page.goto("/audit_log?entity_type=User&action=updated")

    expect(page.get_by_role("heading", name="Audit Log")).to_be_visible()

    cells = page.get_by_role("cell")
    expect(cells.first).to_be_visible()

    user_cell_count = page.locator('css=td:has-text("User")').count()
    assert user_cell_count > 0, "Expected at least one User row after filtering"

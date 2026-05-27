"""Integration tests for the audit_log module."""

from __future__ import annotations

import httpx
import pytest


class TestAuditLogCapture:
    """Verify audit entries are created when entities change."""

    async def test_create_entity_produces_audit_entry(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Creating a setting should produce a 'created' audit entry."""
        await authenticated_client.post(
            "/api/settings/",
            json={
                "scope": "system",
                "scope_id": "",
                "key": "audit.test.key",
                "value": "hello",
                "value_type": "string",
            },
        )

        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"entity_type": "Setting"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        created_entries = [i for i in data["items"] if i["action"] == "created"]
        assert len(created_entries) >= 1
        entry = created_entries[0]
        assert entry["entity_type"] == "Setting"
        assert any(c["field"] == "key" for c in entry["changes"])

    async def test_update_entity_produces_diff(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Updating a setting should record old/new values."""
        create_resp = await authenticated_client.post(
            "/api/settings/",
            json={
                "scope": "system",
                "scope_id": "",
                "key": "audit.update.test",
                "value": "before",
                "value_type": "string",
            },
        )
        setting_id = create_resp.json()["id"]

        await authenticated_client.put(
            f"/api/settings/{setting_id}",
            json={"value": "after"},
        )

        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"entity_type": "Setting", "action": "updated"},
        )
        assert resp.status_code == 200
        data = resp.json()
        update_entries = [i for i in data["items"] if i["action"] == "updated"]
        assert len(update_entries) >= 1
        changes = update_entries[0]["changes"]
        value_change = next((c for c in changes if c["field"] == "value"), None)
        assert value_change is not None
        assert value_change["old"] == "before"
        assert value_change["new"] == "after"

    async def test_delete_entity_produces_audit_entry(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Deleting a setting should produce a 'deleted' entry."""
        create_resp = await authenticated_client.post(
            "/api/settings/",
            json={
                "scope": "system",
                "scope_id": "",
                "key": "audit.delete.test",
                "value": "gone",
                "value_type": "string",
            },
        )
        setting_id = create_resp.json()["id"]

        await authenticated_client.delete(f"/api/settings/{setting_id}")

        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"entity_type": "Setting"},
        )
        assert resp.status_code == 200
        data = resp.json()
        delete_entries = [
            i for i in data["items"] if i["action"] in ("deleted", "soft_deleted")
        ]
        assert len(delete_entries) >= 1


class TestAuditLogAPI:
    """Verify the audit log REST API filtering and pagination."""

    async def test_filter_by_action(self, authenticated_client: httpx.AsyncClient):
        # Ensure at least one "created" entry exists
        await authenticated_client.post(
            "/api/settings/",
            json={
                "scope": "system",
                "scope_id": "",
                "key": "filter.action.test",
                "value": "test",
                "value_type": "string",
            },
        )
        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"action": "created"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) > 0, "Expected at least one 'created' audit entry"
        for item in data["items"]:
            assert item["action"] == "created"

    async def test_pagination(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"page": 1, "page_size": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2

    async def test_unauthenticated_returns_redirect(
        self, client: httpx.AsyncClient
    ):
        resp = await client.get("/api/audit_log/", follow_redirects=False)
        assert resp.status_code in (302, 303, 401, 403)


class TestAuditLogViewInvalidParams:
    """BUG-001: Invalid query params on view routes must not return raw JSON errors."""

    @pytest.mark.parametrize(
        "params",
        [
            {"page": "abc"},
            {"page_size": "0"},
            {"page": "-1"},
            {"page_size": "-5"},
            {"page": "abc", "page_size": "xyz"},
            {"page_size": "999"},
        ],
        ids=[
            "non-integer-page",
            "zero-page-size",
            "negative-page",
            "negative-page-size",
            "both-non-integer",
            "page-size-over-max",
        ],
    )
    async def test_invalid_pagination_returns_html(
        self, authenticated_client: httpx.AsyncClient, params: dict[str, str]
    ):
        """View endpoint should clamp bad pagination values, never 422."""
        resp = await authenticated_client.get(
            "/audit_log/",
            params=params,
            follow_redirects=False,
        )
        # Should succeed (200 full-page) — not a 422 validation error.
        assert resp.status_code == 200, (
            f"Expected 200 for params {params}, got {resp.status_code}: "
            f"{resp.text[:300]}"
        )

    async def test_api_still_rejects_invalid_params(
        self, authenticated_client: httpx.AsyncClient
    ):
        """API endpoint should still return 422 for invalid pagination."""
        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"page_size": "0"},
        )
        assert resp.status_code == 422


class TestAuditLogRecursionGuard:
    """Verify that AuditEntry writes don't trigger more audit entries."""

    async def test_no_infinite_recursion(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Creating a setting should not cause exponential audit entries."""
        await authenticated_client.post(
            "/api/settings/",
            json={
                "scope": "system",
                "scope_id": "",
                "key": "recursion.guard.test",
                "value": "ok",
                "value_type": "string",
            },
        )

        resp = await authenticated_client.get(
            "/api/audit_log/",
            params={"entity_type": "AuditEntry"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0, "AuditEntry should not audit itself"

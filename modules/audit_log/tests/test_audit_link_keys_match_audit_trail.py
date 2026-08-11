"""Registered audit-link keys must match what the audit trail records.

``snapshot_changes`` stores ``type(obj).__name__``, so a registry keyed off
``__tablename__`` never matches. That failure is invisible on the screen:
``entity_link`` falls back to showing ``entity_type`` as the label, so a row
recorded as ``User`` rendered "User <id>" and looked correct while silently
never linking. Only the missing anchor gave it away, in the browser.
"""

from __future__ import annotations

import httpx
from simple_module_core.audit_links import AuditLinkRegistry


class TestRegisteredKeysAreClassNames:
    async def test_user_link_is_keyed_by_class_name(self, app) -> None:
        registry: AuditLinkRegistry = app.state.sm.audit_links
        assert registry.get("User") is not None, sorted(registry.all_links)
        # The table name must NOT be the key — that was the bug.
        assert registry.get("users_user") is None

    async def test_no_key_looks_like_a_table_name(self, app) -> None:
        """`users_user`-style keys are the failure mode; class names are CamelCase."""
        registry: AuditLinkRegistry = app.state.sm.audit_links
        assert registry.all_links, "no module registered an audit link"
        snake = [k for k in registry.all_links if "_" in k or k.islower()]
        assert not snake, f"table-name-style audit link keys will never match: {snake}"

    async def test_audit_rows_resolve_to_a_link_end_to_end(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The real payload the browse screen renders must carry entity URLs."""
        created = await authenticated_client.post(
            "/api/users/admin",
            json={
                "email": "linkcheck@example.com",
                "password": "a-good-password-123",
                "full_name": None,
                "role_names": [],
            },
        )
        assert created.status_code in (200, 201), created.text

        resp = await authenticated_client.get(
            "/audit_log/", headers={"X-Inertia": "true", "Accept": "application/json"}
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["props"]["items"]
        user_rows = [i for i in items if i["entity_type"] == "User"]
        assert user_rows, f"no User audit rows; saw {sorted({i['entity_type'] for i in items})}"
        assert any(r["entity"]["url"] for r in user_rows), (
            "every User row rendered unlinked — the registry key does not match "
            "what snapshot_changes records"
        )

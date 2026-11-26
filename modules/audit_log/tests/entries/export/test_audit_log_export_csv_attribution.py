"""The CSV export says how each change was made (#1242).

PR #1236 records ``auth_kind`` and ``token_id`` on every entry; without them in
the file, an exported log cannot tell a CLI change from a browser one.
"""

from __future__ import annotations

import csv
import io

import httpx
from audit_log.core.constants import ACTION_UPDATED
from audit_log.models import AuditEntry

EXPORT_URL = "/api/audit_log/export.csv"


async def test_export_carries_auth_kind_and_token_id(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    async with app.state.sm.db.session_factory() as session:
        session.add_all(
            [
                AuditEntry(
                    entity_type="Widget", entity_id="by-token", action=ACTION_UPDATED,
                    changes=[], auth_kind="pat", token_id="tok-123",
                ),
                AuditEntry(
                    entity_type="Widget", entity_id="by-browser", action=ACTION_UPDATED,
                    changes=[], auth_kind="session",
                ),
                AuditEntry(
                    entity_type="Widget", entity_id="by-system", action=ACTION_UPDATED,
                    changes=[],
                ),
            ]
        )  # fmt: skip
        await session.commit()

    resp = await authenticated_client.get(EXPORT_URL, params={"entity_type": "Widget"})

    assert resp.status_code == 200, resp.text
    rows = {r["entity_id"]: r for r in csv.DictReader(io.StringIO(resp.text))}
    assert (rows["by-token"]["auth_kind"], rows["by-token"]["token_id"]) == ("pat", "tok-123")
    assert (rows["by-browser"]["auth_kind"], rows["by-browser"]["token_id"]) == ("session", "")
    assert (rows["by-system"]["auth_kind"], rows["by-system"]["token_id"]) == ("", "")

"""Shared fixtures for the entity-label tests.

Split out so the label tests and the batching tests can live in separate
files without either growing a second copy of "seed one row, read the page
back, find its entity cell".
"""

from __future__ import annotations

import httpx
from audit_log.constants import ACTION_UPDATED
from audit_log.models import AuditEntry

VIEW_URL = "/admin/audit-log/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}


async def browse(client: httpx.AsyncClient, **params: str) -> dict:
    resp = await client.get(VIEW_URL, params=params, headers=INERTIA_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


def entity_of(props: dict, entity_id: str) -> dict:
    matches = [i["entity"] for i in props["items"] if i["entity_id"] == entity_id]
    assert matches, f"no audit row for {entity_id!r} in {[i['entity_id'] for i in props['items']]}"
    return matches[0]


async def seed_entry(app, *, entity_type: str, entity_id: str) -> None:
    async with app.state.sm.db.session_factory() as session:
        session.add(
            AuditEntry(
                entity_type=entity_type,
                entity_id=entity_id,
                action=ACTION_UPDATED,
                changes=[{"field": "x", "old": 1, "new": 2}],
            )
        )
        await session.commit()

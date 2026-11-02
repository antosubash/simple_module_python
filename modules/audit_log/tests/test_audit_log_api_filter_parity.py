"""JSON list and CSV export interpret the same query identically (#698)."""

import csv
import io
import uuid
from datetime import UTC, datetime

import pytest
from audit_log.constants import ACTION_UPDATED
from audit_log.models import AuditEntry
from users.models import User


@pytest.mark.parametrize("actor", ["", "Filter Person", "filter-person@example.com", "id"])
async def test_audit_log_list_matches_export_actor_and_day(app, authenticated_client, actor):
    user_id = uuid.uuid4()
    async with app.state.sm.db.session_factory() as db:
        db.add(
            User(
                id=user_id,
                email="filter-person@example.com",
                full_name="Filter Person",
                hashed_password="unused",
            )
        )
        await db.flush()
        for entity_id, day in [("included", 19), ("excluded", 20)]:
            db.add(
                AuditEntry(
                    entity_type="FilterParity",
                    entity_id=entity_id,
                    action=ACTION_UPDATED,
                    changes=[],
                    user_id=str(user_id),
                    created_at=datetime(2026, 8, day, 14, tzinfo=UTC),
                )
            )
        await db.commit()
    params = {
        "entity_type": "FilterParity",
        "to_date": "2026-08-19",
        "user_id": str(user_id) if actor == "id" else actor,
    }
    listing = await authenticated_client.get("/api/audit_log/", params=params)
    export = await authenticated_client.get("/api/audit_log/export.csv", params=params)
    assert listing.status_code == export.status_code == 200
    assert [row["entity_id"] for row in csv.DictReader(io.StringIO(export.text))] == ["included"]
    assert [row["entity_id"] for row in listing.json()["items"]] == ["included"]

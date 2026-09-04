"""The Date range control is date-only, and the server has to mean it.

"To 19 Aug" parses as 19 Aug 00:00:00. Compared with ``<=`` that excludes
everything that happened on the day the reader just picked as the end of their
range — on the usual "up to today" case, the part they came for. The stretch
belongs to the constructor the screen uses, not to some other step that happens
to run nearby.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from audit_log.constants import ACTION_UPDATED
from audit_log.filters import EntryFilters
from audit_log.models import AuditEntry

VIEW_URL = "/admin/audit-log/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}
_ENTITY_TYPE = "Widget"


async def _entity_ids(client: httpx.AsyncClient, **params: str) -> list[str]:
    resp = await client.get(
        VIEW_URL, params={"entity_type": _ENTITY_TYPE, **params}, headers=INERTIA_HEADERS
    )
    assert resp.status_code == 200, resp.text
    return sorted(item["entity_id"] for item in resp.json()["props"]["items"])


class TestDateRange:
    """The picker is date-only, so ``to_date`` names a whole day. Treating it
    as midnight silently excludes everything that happened on the day the
    reader just chose as the end of the range."""

    def test_the_screen_constructor_stretches_the_upper_bound(self) -> None:
        """Named for what it does, and it does it whatever else was filtered —
        the stretch used to ride along inside the actor step, where a caller
        with no Actor term would have missed it."""
        filters = EntryFilters.for_date_only_range(to_date=datetime(2026, 8, 19, tzinfo=UTC))

        assert filters.actor_match is None
        assert filters.to_date == datetime(2026, 8, 19, 23, 59, 59, 999999, tzinfo=UTC)

    def test_plain_construction_keeps_the_exact_bound(self) -> None:
        """The JSON list endpoint documents ``to_date`` as a timestamp; only
        the screen's date-only control needs stretching."""
        exact = datetime(2026, 8, 19, 10, 30, tzinfo=UTC)

        assert EntryFilters(to_date=exact).to_date == exact

    async def test_to_date_includes_the_whole_day(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        stamp = datetime(2026, 8, 19, 14, 2, 11, tzinfo=UTC)
        async with app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id="afternoon",
                    action=ACTION_UPDATED,
                    changes=[],
                    created_at=stamp,
                )
            )
            await session.commit()

        found = await _entity_ids(
            authenticated_client, from_date="2026-08-01", to_date="2026-08-19"
        )

        assert found == ["afternoon"]

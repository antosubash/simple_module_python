"""The dashboard's "+{n} this month" delta on the Total users card.

The deck shows growth beside the headline figure. Nothing in the payload could
supply it, so the tile either shipped without the delta or with an invented
one; this pins the real count of accounts created since the first of the
current month.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from dashboard.stats import fetch_dashboard_stats, invalidate_stats_cache
from users.models import User


@pytest.fixture(autouse=True)
def _clear_stats_cache():
    invalidate_stats_cache()
    yield
    invalidate_stats_cache()


def _start_of_month(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _seed(app, *offsets: datetime) -> None:
    async with app.state.sm.db.session_factory() as session:
        for index, created in enumerate(offsets):
            session.add(
                User(
                    email=f"month-delta-{index}-{created.timestamp()}@example.com",
                    hashed_password="x",
                    is_active=True,
                    created_at=created,
                )
            )
        await session.commit()


async def _stats(app) -> dict:
    async with app.state.sm.db.session_factory() as db:
        return await fetch_dashboard_stats(db, app)


class TestUsersCreatedThisMonth:
    async def test_the_stat_is_reported(self, app) -> None:
        assert "users_created_this_month" in await _stats(app)

    async def test_only_this_months_accounts_are_counted(self, app) -> None:
        now = datetime.now(UTC)
        before = (await _stats(app))["users_created_this_month"]
        invalidate_stats_cache()

        await _seed(
            app,
            now,
            _start_of_month(now),
            _start_of_month(now) - timedelta(seconds=1),
            now - timedelta(days=90),
        )

        after = (await _stats(app))["users_created_this_month"]
        # The account created exactly at the month boundary counts; the one a
        # second earlier belongs to last month.
        assert after == before + 2

    async def test_it_never_exceeds_the_total(self, app) -> None:
        stats = await _stats(app)
        assert stats["users_created_this_month"] <= stats["total_users"]


class TestDashboardView:
    async def test_the_page_receives_the_delta(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(
            "/dashboard/", headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"}
        )

        assert resp.status_code == 200, resp.text
        props = resp.json()["props"]
        assert isinstance(props["users_created_this_month"], int)
        assert props["users_created_this_month"] >= 1, "the seeded admin was created just now"

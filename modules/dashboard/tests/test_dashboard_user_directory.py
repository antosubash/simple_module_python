"""Dashboard user tiles come from the user directory (GH #501)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from simple_module_core.user_directory import (
    DirectoryStats,
    NullUserDirectory,
    get_user_directory,
    set_user_directory,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    from dashboard.stats import invalidate_stats_cache

    invalidate_stats_cache()
    yield
    invalidate_stats_cache()


class _KeycloakLike(NullUserDirectory):
    """Knows how many signed in, not when the accounts were created."""

    def __init__(self) -> None:
        self.windows: list[timedelta] = []

    async def stats(self, db, *, active_window):
        self.windows.append(active_window)
        return DirectoryStats(total=4, active_since=2, created_this_month=None)


async def _stats(app) -> dict:
    from dashboard.stats import fetch_dashboard_stats

    async with app.state.sm.db.session_factory() as db:
        return await fetch_dashboard_stats(db, app)


async def test_counts_come_from_the_directory(app):
    original = get_user_directory(app)
    directory = _KeycloakLike()
    set_user_directory(app, directory)
    try:
        stats = await _stats(app)
    finally:
        set_user_directory(app, original)
    assert stats["total_users"] == 4
    assert stats["active_users_7d"] == 2
    # Unknown, not zero: the page hides the "+N this month" delta.
    assert stats["users_created_this_month"] is None
    assert directory.windows == [timedelta(days=7)]


async def test_no_directory_hides_every_user_tile(app):
    original = get_user_directory(app)
    set_user_directory(app, NullUserDirectory())
    try:
        stats = await _stats(app)
    finally:
        set_user_directory(app, original)
    assert stats["total_users"] is None
    assert stats["active_users_7d"] is None
    assert stats["users_created_this_month"] is None
    # The rest of the dashboard is unaffected.
    assert stats["module_count"] >= 1

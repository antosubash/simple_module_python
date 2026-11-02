"""Shared UTC helpers preserve aware values and interpret naive values as UTC."""

from datetime import UTC, datetime, timedelta, timezone

from simple_module_core.datetimes import aware, utcnow


def test_naive_is_utc_and_aware_keeps_its_offset():
    naive = datetime(2026, 1, 1)
    assert aware(naive) == datetime(2026, 1, 1, tzinfo=UTC)
    offset = naive.replace(tzinfo=timezone(timedelta(hours=2)))
    assert aware(offset) is offset


def test_utcnow_is_current_aware_utc():
    before = datetime.now(UTC)
    value = utcnow()
    assert before <= value <= datetime.now(UTC)
    assert value.tzinfo is UTC

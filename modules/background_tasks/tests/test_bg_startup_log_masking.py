"""The startup line must not leak the broker URL's password."""

from __future__ import annotations

import pytest

SECRET = "hunter2-broker-pw"


@pytest.fixture
def _broker_with_password(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    monkeypatch.setenv("SM_REDIS_URL", f"redis://user:{SECRET}@localhost:6399/0")


async def test_startup_log_masks_broker_password(
    _broker_with_password, caplog: pytest.LogCaptureFixture, app
) -> None:
    # The app fixture boots during setup, so read the setup-phase records.
    records = caplog.get_records("setup")
    ready = [r for r in records if "Celery app ready" in r.getMessage()]
    assert ready, "startup log line not captured"
    assert "user:***@localhost" in ready[0].getMessage()
    assert all(SECRET not in r.getMessage() for r in records)

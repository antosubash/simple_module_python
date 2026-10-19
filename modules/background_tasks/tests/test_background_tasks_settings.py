from __future__ import annotations

import pytest
from background_tasks.settings import BackgroundTasksSettings
from pydantic import ValidationError


@pytest.mark.parametrize("retention_days", [1, 3650])
def test_retention_days_accepts_supported_boundaries(retention_days: int) -> None:
    assert BackgroundTasksSettings(retention_days=retention_days).retention_days == retention_days


@pytest.mark.parametrize("retention_days", [0, -5, 3651, 999_999_999])
def test_retention_days_rejects_values_outside_supported_range(retention_days: int) -> None:
    with pytest.raises(ValidationError):
        BackgroundTasksSettings(retention_days=retention_days)


@pytest.mark.parametrize("max_retries", [0, 100])
def test_max_retries_accepts_supported_boundaries(max_retries: int) -> None:
    assert BackgroundTasksSettings(max_retries=max_retries).max_retries == max_retries


@pytest.mark.parametrize("max_retries", [-1, 101, 999_999_999])
def test_max_retries_rejects_values_outside_supported_range(max_retries: int) -> None:
    with pytest.raises(ValidationError):
        BackgroundTasksSettings(max_retries=max_retries)


def test_soft_time_limit_must_be_below_hard_limit() -> None:
    ok = BackgroundTasksSettings(task_soft_time_limit=50, task_time_limit=100)
    assert (ok.task_soft_time_limit, ok.task_time_limit) == (50, 100)
    assert BackgroundTasksSettings(task_soft_time_limit=50).task_time_limit is None
    assert BackgroundTasksSettings(task_time_limit=50).task_soft_time_limit is None

    for soft, hard in ((100, 50), (50, 50)):
        with pytest.raises(ValidationError) as exc:
            BackgroundTasksSettings(task_soft_time_limit=soft, task_time_limit=hard)
        err = exc.value.errors()[0]
        assert err["loc"] == ("task_time_limit",)
        assert "task_soft_time_limit" in err["msg"]


@pytest.mark.asyncio
async def test_stored_invalid_limit_pair_does_not_break_lenient_hydration(db_session) -> None:
    from settings.hydrate import hydrate_settings
    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    await store.set_override("background_tasks", "task_soft_time_limit", "100", "int")
    await store.set_override("background_tasks", "task_time_limit", "50", "int")
    cfg = await hydrate_settings(
        BackgroundTasksSettings, store, package="background_tasks", lenient=True
    )
    assert cfg.task_soft_time_limit == 100
    assert cfg.task_time_limit is None


@pytest.mark.asyncio
async def test_editor_reports_the_limit_pair_on_the_hard_limit(authenticated_client) -> None:
    resp = await authenticated_client.put(
        "/api/settings/modules/background_tasks",
        json={"task_soft_time_limit": 100, "task_time_limit": 50},
    )

    assert resp.status_code == 422
    [error] = resp.json()["detail"]
    assert error["loc"][-1] == "task_time_limit"
    assert "task_soft_time_limit" in error["msg"]

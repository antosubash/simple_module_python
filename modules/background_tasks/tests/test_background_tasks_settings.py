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


@pytest.mark.parametrize(("soft", "hard"), [(30, 60), (None, 60), (100, None), (None, None)])
def test_time_limits_accept_a_soft_limit_below_the_hard_one(
    soft: int | None, hard: int | None
) -> None:
    cfg = BackgroundTasksSettings(task_soft_time_limit=soft, task_time_limit=hard)
    assert (cfg.task_soft_time_limit, cfg.task_time_limit) == (soft, hard)


@pytest.mark.parametrize(("soft", "hard"), [(100, 50), (60, 60)])
def test_time_limits_reject_a_soft_limit_that_could_never_fire(soft: int, hard: int) -> None:
    with pytest.raises(ValidationError) as exc:
        BackgroundTasksSettings(task_soft_time_limit=soft, task_time_limit=hard)
    # Located on the soft field, so lenient hydration drops that row and keeps the hard kill.
    assert [e["loc"] for e in exc.value.errors()] == [("task_soft_time_limit",)]

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

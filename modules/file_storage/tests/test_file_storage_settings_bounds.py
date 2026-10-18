"""``quota_bytes`` is either unset (unmeasured) or a positive total (GH #548)."""

from __future__ import annotations

import pytest
from file_storage.settings import FileStorageSettings
from pydantic import ValidationError


@pytest.mark.parametrize("quota", [None, 1, 5 * 1024**3])
def test_quota_bytes_accepts_unset_or_positive(quota: int | None) -> None:
    assert FileStorageSettings(quota_bytes=quota).quota_bytes == quota


@pytest.mark.parametrize("quota", [0, -1])
def test_quota_bytes_rejects_non_positive(quota: int) -> None:
    with pytest.raises(ValidationError) as exc:
        FileStorageSettings(quota_bytes=quota)
    assert [e["loc"] for e in exc.value.errors()] == [("quota_bytes",)]

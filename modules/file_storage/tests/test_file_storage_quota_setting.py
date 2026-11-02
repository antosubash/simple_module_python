"""``quota_bytes`` must be a positive, JS-safe byte count or unset (#548)."""

from __future__ import annotations

import pytest
from file_storage import constants
from file_storage.settings import FileStorageSettings
from pydantic import ValidationError

_API = "/api/settings/modules/file_storage"


@pytest.mark.parametrize("value", [-1, 0, constants.MAX_JS_SAFE_INTEGER + 1, 2**63])
def test_out_of_range_quota_is_rejected(value):
    with pytest.raises(ValidationError):
        FileStorageSettings(quota_bytes=value)


@pytest.mark.parametrize("value", [None, 1, 5 * 1024**3, constants.MAX_JS_SAFE_INTEGER])
def test_unset_or_positive_quota_is_accepted(value):
    assert FileStorageSettings(quota_bytes=value).quota_bytes == value


async def test_settings_api_refuses_a_negative_quota(authenticated_client, app):
    resp = await authenticated_client.put(_API, json={"quota_bytes": -1})

    assert resp.status_code == 422, resp.text
    assert app.state.file_storage.settings.quota_bytes is None

    resp = await authenticated_client.put(_API, json={"quota_bytes": 1024})
    assert resp.status_code == 200, resp.text
    assert app.state.file_storage.settings.quota_bytes == 1024

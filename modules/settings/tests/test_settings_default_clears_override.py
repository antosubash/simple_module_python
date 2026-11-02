"""Saving a field's default removes its override row instead of storing it."""

from __future__ import annotations

import pytest
from background_tasks.settings import DEFAULT_RETENTION_DAYS
from settings.service import SettingService
from settings.store import SettingsStore

URL = "/api/settings/modules"


async def _overrides(app, package: str) -> dict:
    async with app.state.sm.db.session_factory() as db:
        return await SettingsStore(SettingService(db)).get_overrides(package)


async def _field(client, package: str, name: str) -> dict:
    resp = await client.get(URL)
    module = next(m for m in resp.json()["modules"] if m["package"] == package)
    return next(f for f in module["fields"] if f["name"] == name)


@pytest.mark.asyncio
async def test_clearing_optional_field_removes_row_and_reports_default(authenticated_client, app):
    put = authenticated_client.put
    assert (await put(f"{URL}/file_storage", json={"quota_bytes": 1000})).status_code == 200
    assert "quota_bytes" in await _overrides(app, "file_storage")

    resp = await put(f"{URL}/file_storage", json={"quota_bytes": None})

    assert resp.status_code == 200, resp.text
    assert "quota_bytes" not in await _overrides(app, "file_storage")
    field = await _field(authenticated_client, "file_storage", "quota_bytes")
    assert field["source"] == "default"
    assert not field["db_override"]
    assert app.state.file_storage.settings.quota_bytes is None


@pytest.mark.asyncio
async def test_non_default_value_is_still_stored(authenticated_client, app):
    resp = await authenticated_client.put(f"{URL}/file_storage", json={"quota_bytes": 1000})

    assert resp.status_code == 200, resp.text
    assert "quota_bytes" in await _overrides(app, "file_storage")
    field = await _field(authenticated_client, "file_storage", "quota_bytes")
    assert field["source"] == "db"


@pytest.mark.asyncio
async def test_value_equal_to_non_none_default_removes_row(authenticated_client, app):
    put = authenticated_client.put
    assert (await put(f"{URL}/background_tasks", json={"retention_days": 7})).status_code == 200
    assert "retention_days" in await _overrides(app, "background_tasks")

    resp = await put(f"{URL}/background_tasks", json={"retention_days": DEFAULT_RETENTION_DAYS})

    assert resp.status_code == 200, resp.text
    assert "retention_days" not in await _overrides(app, "background_tasks")
    field = await _field(authenticated_client, "background_tasks", "retention_days")
    assert field["source"] == "default"


@pytest.mark.asyncio
async def test_noop_save_removes_a_legacy_null_row(authenticated_client, app):
    async with app.state.sm.db.session_factory() as db:
        await SettingsStore(SettingService(db)).set_override(
            "file_storage", "quota_bytes", "null", "json"
        )
        await db.commit()
    field = await _field(authenticated_client, "file_storage", "quota_bytes")
    assert field["db_override"]

    resp = await authenticated_client.put(f"{URL}/file_storage", json={"quota_bytes": None})

    assert resp.status_code == 200, resp.text
    assert "quota_bytes" not in await _overrides(app, "file_storage")
    field = await _field(authenticated_client, "file_storage", "quota_bytes")
    assert field["source"] == "default"
    assert not field["db_override"]

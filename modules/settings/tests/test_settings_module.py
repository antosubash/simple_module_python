"""Tests for the Settings module: service CRUD, API endpoints, schema validation."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError
from settings.contracts.schemas import (
    SettingCreate,
    SettingUpdate,
)
from settings.service import SettingService
from sqlalchemy.ext.asyncio import AsyncSession

# ── Schema validation ────────────────────────────────────────────────


class TestSettingSchemas:
    async def test_create_valid(self):
        data = SettingCreate(name="Test Setting")
        assert data.name == "Test Setting"
        assert data.description is None

    async def test_create_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            SettingCreate(name="")

    async def test_update_all_optional(self):
        data = SettingUpdate()
        assert data.name is None
        assert data.is_active is None


# ── SettingService CRUD ──────────────────────────────────────────────


class TestSettingService:
    async def test_create(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        item = await svc.create(SettingCreate(name="Test"))
        assert item.id is not None
        assert item.name == "Test"
        assert item.is_active is True

    async def test_get_all(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.create(SettingCreate(name="A"))
        await svc.create(SettingCreate(name="B"))
        items = await svc.get_all()
        assert len(items) == 2

    async def test_get_by_id(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        created = await svc.create(SettingCreate(name="X"))
        found = await svc.get_by_id(created.id)
        assert found is not None
        assert found.name == "X"

    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        found = await svc.get_by_id(999)
        assert found is None

    async def test_update(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        created = await svc.create(SettingCreate(name="Old"))
        updated = await svc.update(created.id, SettingUpdate(name="New"))
        assert updated is not None
        assert updated.name == "New"

    async def test_update_not_found(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        result = await svc.update(999, SettingUpdate(name="Ghost"))
        assert result is None

    async def test_delete(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        created = await svc.create(SettingCreate(name="Doomed"))
        deleted = await svc.delete(created.id)
        assert deleted is True

    async def test_delete_not_found(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        deleted = await svc.delete(999)
        assert deleted is False


# ── API endpoints ───────────────────────────────────────────────


class TestSettingsAPI:
    async def test_list_empty(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/settings/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(
            "/api/settings/",
            json={"name": "Test Setting"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Setting"
        assert data["id"] is not None

    async def test_get_by_id(self, authenticated_client: httpx.AsyncClient):
        create_resp = await authenticated_client.post(
            "/api/settings/",
            json={"name": "Findable"},
        )
        item_id = create_resp.json()["id"]
        resp = await authenticated_client.get(f"/api/settings/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Findable"

    async def test_get_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/settings/99999")
        assert resp.status_code == 404

    async def test_update(self, authenticated_client: httpx.AsyncClient):
        create_resp = await authenticated_client.post(
            "/api/settings/",
            json={"name": "Original"},
        )
        item_id = create_resp.json()["id"]
        resp = await authenticated_client.put(
            f"/api/settings/{item_id}",
            json={"name": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    async def test_delete(self, authenticated_client: httpx.AsyncClient):
        create_resp = await authenticated_client.post(
            "/api/settings/",
            json={"name": "Deletable"},
        )
        item_id = create_resp.json()["id"]
        resp = await authenticated_client.delete(f"/api/settings/{item_id}")
        assert resp.status_code == 204

    async def test_delete_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.delete("/api/settings/99999")
        assert resp.status_code == 404

    async def test_create_invalid_data(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(
            "/api/settings/",
            json={"name": ""},
        )
        assert resp.status_code == 422


# ── Module lifecycle ────────────────────────────────────────────────


class TestSettingsModuleLifecycle:
    async def test_on_startup_does_not_call_create_all(self):
        """on_startup should not create tables — Alembic manages schema."""
        from unittest.mock import AsyncMock, MagicMock

        from settings.module import SettingsModule

        mod = SettingsModule()
        mock_app = MagicMock()
        mock_app.state.sm.db.engine = AsyncMock()

        await mod.on_startup(mock_app)

        mock_app.state.sm.db.engine.begin.assert_not_called()

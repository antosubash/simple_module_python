"""Tests for the Catalog module: service CRUD, API endpoints, schema validation."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError
from catalog.contracts.schemas import (
    CatalogCreate,
    CatalogUpdate,
)
from catalog.service import CatalogService
from sqlalchemy.ext.asyncio import AsyncSession

# ── Schema validation ────────────────────────────────────────────────


class TestCatalogSchemas:
    async def test_create_valid(self):
        data = CatalogCreate(name="Test Catalog")
        assert data.name == "Test Catalog"
        assert data.description is None

    async def test_create_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            CatalogCreate(name="")

    async def test_update_all_optional(self):
        data = CatalogUpdate()
        assert data.name is None
        assert data.is_active is None


# ── CatalogService CRUD ──────────────────────────────────────────────


class TestCatalogService:
    async def test_create(self, db_session: AsyncSession):
        svc = CatalogService(db_session)
        item = await svc.create(CatalogCreate(name="Test"))
        assert item.id is not None
        assert item.name == "Test"
        assert item.is_active is True

    async def test_get_all(self, db_session: AsyncSession):
        svc = CatalogService(db_session)
        await svc.create(CatalogCreate(name="A"))
        await svc.create(CatalogCreate(name="B"))
        items = await svc.get_all()
        assert len(items) == 2

    async def test_get_by_id(self, db_session: AsyncSession):
        svc = CatalogService(db_session)
        created = await svc.create(CatalogCreate(name="X"))
        found = await svc.get_by_id(created.id)
        assert found is not None
        assert found.name == "X"

    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        svc = CatalogService(db_session)
        found = await svc.get_by_id(999)
        assert found is None

    async def test_update(self, db_session: AsyncSession):
        svc = CatalogService(db_session)
        created = await svc.create(CatalogCreate(name="Old"))
        updated = await svc.update(created.id, CatalogUpdate(name="New"))
        assert updated is not None
        assert updated.name == "New"

    async def test_update_not_found(self, db_session: AsyncSession):
        svc = CatalogService(db_session)
        result = await svc.update(999, CatalogUpdate(name="Ghost"))
        assert result is None

    async def test_delete(self, db_session: AsyncSession):
        svc = CatalogService(db_session)
        created = await svc.create(CatalogCreate(name="Doomed"))
        deleted = await svc.delete(created.id)
        assert deleted is True

    async def test_delete_not_found(self, db_session: AsyncSession):
        svc = CatalogService(db_session)
        deleted = await svc.delete(999)
        assert deleted is False


# ── API endpoints ───────────────────────────────────────────────


class TestCatalogAPI:
    async def test_list_empty(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/catalog/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(
            "/api/catalog/",
            json={"name": "Test Catalog"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Catalog"
        assert data["id"] is not None

    async def test_get_by_id(self, authenticated_client: httpx.AsyncClient):
        create_resp = await authenticated_client.post(
            "/api/catalog/",
            json={"name": "Findable"},
        )
        item_id = create_resp.json()["id"]
        resp = await authenticated_client.get(f"/api/catalog/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Findable"

    async def test_get_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/catalog/99999")
        assert resp.status_code == 404

    async def test_update(self, authenticated_client: httpx.AsyncClient):
        create_resp = await authenticated_client.post(
            "/api/catalog/",
            json={"name": "Original"},
        )
        item_id = create_resp.json()["id"]
        resp = await authenticated_client.put(
            f"/api/catalog/{item_id}",
            json={"name": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    async def test_delete(self, authenticated_client: httpx.AsyncClient):
        create_resp = await authenticated_client.post(
            "/api/catalog/",
            json={"name": "Deletable"},
        )
        item_id = create_resp.json()["id"]
        resp = await authenticated_client.delete(f"/api/catalog/{item_id}")
        assert resp.status_code == 204

    async def test_delete_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.delete("/api/catalog/99999")
        assert resp.status_code == 404

    async def test_create_invalid_data(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(
            "/api/catalog/",
            json={"name": ""},
        )
        assert resp.status_code == 422


# ── Module lifecycle ────────────────────────────────────────────────


class TestCatalogModuleLifecycle:
    async def test_on_startup_does_not_call_create_all(self):
        """on_startup should not create tables — Alembic manages schema."""
        from unittest.mock import AsyncMock, MagicMock

        from catalog.module import CatalogModule

        mod = CatalogModule()
        mock_app = MagicMock()
        mock_app.state.sm.db.engine = AsyncMock()

        await mod.on_startup(mock_app)

        mock_app.state.sm.db.engine.begin.assert_not_called()

"""Tests for the Settings module: service CRUD/upsert, API endpoints, schemas."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError
from settings.constants import (
    API_PREFIX,
    PERM_CREATE,
    PERM_DELETE,
    PERM_EDIT,
    PERM_VIEW,
    STATUS_CONFLICT,
    STATUS_CREATED,
    STATUS_NO_CONTENT,
    STATUS_NOT_FOUND,
)
from settings.contracts.schemas import (
    SettingCreate,
    SettingUpdate,
    SettingUpsert,
)
from settings.service import SettingService
from sqlalchemy.ext.asyncio import AsyncSession

# ── Schema validation ────────────────────────────────────────────────


class TestSettingSchemas:
    async def test_create_valid(self):
        data = SettingCreate(key="feature.enabled", value="true")
        assert data.key == "feature.enabled"
        assert data.value == "true"

    async def test_create_empty_key_rejected(self):
        with pytest.raises(ValidationError):
            SettingCreate(key="", value="true")

    async def test_update_all_optional(self):
        data = SettingUpdate()
        assert data.value is None
        assert data.description is None

    async def test_upsert_requires_value(self):
        with pytest.raises(ValidationError):
            SettingUpsert()  # ty: ignore[missing-argument]


# ── SettingService ──────────────────────────────────────────────────


class TestSettingService:
    async def test_create(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        item = await svc.create(SettingCreate(key="k1", value="v1"))
        assert item.id is not None
        assert item.key == "k1"
        assert item.value == "v1"

    async def test_list_all_sorted_by_key(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.create(SettingCreate(key="b.key", value="2"))
        await svc.create(SettingCreate(key="a.key", value="1"))
        items = await svc.list_all()
        assert [i.key for i in items] == ["a.key", "b.key"]

    async def test_get_by_id(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        created = await svc.create(SettingCreate(key="k", value="v"))
        assert created.id is not None
        found = await svc.get_by_id(created.id)
        assert found is not None
        assert found.key == "k"

    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        assert await svc.get_by_id(999) is None

    async def test_get_by_key(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.create(SettingCreate(key="lookup.key", value="hello"))
        found = await svc.get_by_key("lookup.key")
        assert found is not None
        assert found.value == "hello"

    async def test_get_value(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.create(SettingCreate(key="x.y", value="42"))
        assert await svc.get_value("x.y") == "42"
        assert await svc.get_value("missing", default="fallback") == "fallback"
        assert await svc.get_value("missing") is None

    async def test_update(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        created = await svc.create(SettingCreate(key="k", value="old"))
        assert created.id is not None
        updated = await svc.update(created.id, SettingUpdate(value="new"))
        assert updated is not None
        assert updated.value == "new"
        assert updated.key == "k"

    async def test_update_not_found(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        assert await svc.update(999, SettingUpdate(value="x")) is None

    async def test_upsert_creates_when_missing(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        result = await svc.upsert_by_key("new.key", SettingUpsert(value="v", description="d"))
        assert result.key == "new.key"
        assert result.value == "v"
        assert result.description == "d"

    async def test_upsert_updates_when_present(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.create(SettingCreate(key="k", value="old"))
        result = await svc.upsert_by_key("k", SettingUpsert(value="new"))
        assert result.value == "new"
        all_items = await svc.list_all()
        assert len(all_items) == 1

    async def test_delete(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        created = await svc.create(SettingCreate(key="k", value="v"))
        assert created.id is not None
        assert await svc.delete(created.id) is True
        assert await svc.get_by_id(created.id) is None

    async def test_delete_not_found(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        assert await svc.delete(999) is False

    async def test_delete_by_key(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        await svc.create(SettingCreate(key="k", value="v"))
        assert await svc.delete_by_key("k") is True
        assert await svc.get_by_key("k") is None

    async def test_delete_by_key_not_found(self, db_session: AsyncSession):
        svc = SettingService(db_session)
        assert await svc.delete_by_key("missing") is False


# ── API endpoints ───────────────────────────────────────────────────


def _url(path: str = "") -> str:
    return f"{API_PREFIX}/{path.lstrip('/')}" if path else f"{API_PREFIX}/"


class TestSettingsAPI:
    async def test_list_empty(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(_url())
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(_url(), json={"key": "a.b", "value": "v"})
        assert resp.status_code == STATUS_CREATED
        data = resp.json()
        assert data["key"] == "a.b"
        assert data["value"] == "v"
        assert data["id"] is not None

    async def test_get_by_id(self, authenticated_client: httpx.AsyncClient):
        created = await authenticated_client.post(_url(), json={"key": "k", "value": "v"})
        item_id = created.json()["id"]
        resp = await authenticated_client.get(_url(str(item_id)))
        assert resp.status_code == 200
        assert resp.json()["key"] == "k"

    async def test_get_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(_url("99999"))
        assert resp.status_code == STATUS_NOT_FOUND

    async def test_get_by_key(self, authenticated_client: httpx.AsyncClient):
        await authenticated_client.post(_url(), json={"key": "lookup", "value": "hi"})
        resp = await authenticated_client.get(_url("by-key/lookup"))
        assert resp.status_code == 200
        assert resp.json()["value"] == "hi"

    async def test_get_by_key_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(_url("by-key/missing"))
        assert resp.status_code == STATUS_NOT_FOUND

    async def test_update(self, authenticated_client: httpx.AsyncClient):
        created = await authenticated_client.post(_url(), json={"key": "k", "value": "old"})
        item_id = created.json()["id"]
        resp = await authenticated_client.put(_url(str(item_id)), json={"value": "new"})
        assert resp.status_code == 200
        assert resp.json()["value"] == "new"

    async def test_upsert_by_key_creates(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(_url("by-key/new.key"), json={"value": "v"})
        assert resp.status_code == 200
        assert resp.json()["key"] == "new.key"

    async def test_upsert_by_key_updates(self, authenticated_client: httpx.AsyncClient):
        await authenticated_client.post(_url(), json={"key": "k", "value": "old"})
        resp = await authenticated_client.put(_url("by-key/k"), json={"value": "new"})
        assert resp.status_code == 200
        assert resp.json()["value"] == "new"

    async def test_delete(self, authenticated_client: httpx.AsyncClient):
        created = await authenticated_client.post(_url(), json={"key": "k", "value": "v"})
        item_id = created.json()["id"]
        resp = await authenticated_client.delete(_url(str(item_id)))
        assert resp.status_code == STATUS_NO_CONTENT

    async def test_delete_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.delete(_url("99999"))
        assert resp.status_code == STATUS_NOT_FOUND

    async def test_delete_by_key(self, authenticated_client: httpx.AsyncClient):
        await authenticated_client.post(_url(), json={"key": "k", "value": "v"})
        resp = await authenticated_client.delete(_url("by-key/k"))
        assert resp.status_code == STATUS_NO_CONTENT

    async def test_create_invalid_empty_key(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(_url(), json={"key": "", "value": "v"})
        assert resp.status_code == 422


# ── Module registration / constants ─────────────────────────────────


class TestSettingsModuleRegistration:
    async def test_permissions_registered(self, app):
        perms = set(app.state.sm.permissions.all_permissions)
        for p in (PERM_VIEW, PERM_CREATE, PERM_EDIT, PERM_DELETE):
            assert p in perms

    async def test_all_permissions_unique(self):
        from settings.constants import ALL_PERMISSIONS

        assert len(ALL_PERMISSIONS) == len(set(ALL_PERMISSIONS))

    async def test_status_constants(self):
        assert STATUS_CREATED == 201
        assert STATUS_NO_CONTENT == 204
        assert STATUS_NOT_FOUND == 404
        assert STATUS_CONFLICT == 409

    async def test_view_page_literals_match_constants(self):
        """Views use literal inertia.render(...) strings so SM003 can detect
        them — this guards the literals against drifting from the constants."""
        from pathlib import Path

        from settings.constants import PAGE_BROWSE, PAGE_CREATE, PAGE_EDIT

        views = (Path(__file__).parent.parent / "settings" / "endpoints" / "views.py").read_text()
        assert f'"{PAGE_BROWSE}"' in views
        assert f'"{PAGE_CREATE}"' in views
        assert f'"{PAGE_EDIT}"' in views

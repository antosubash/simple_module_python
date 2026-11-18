"""Tests for the {{MODULE_NAME}} crud feature."""

# ruff: noqa: I001

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from {{PACKAGE_NAME}}.contracts.schemas import {{SINGULAR_CLASS}}Create, {{SINGULAR_CLASS}}Update
from {{PACKAGE_NAME}}.web.service import {{SINGULAR_CLASS}}Service

API = "/api/{{MODULE_SLUG}}/"


class TestService:
    async def test_create(self, db_session: AsyncSession):
        svc = {{SINGULAR_CLASS}}Service(db_session)
        item = await svc.create({{SINGULAR_CLASS}}Create(name="Test"))
        assert item.id is not None
        assert item.is_active is True

    async def test_get_all(self, db_session: AsyncSession):
        svc = {{SINGULAR_CLASS}}Service(db_session)
        await svc.create({{SINGULAR_CLASS}}Create(name="A"))
        await svc.create({{SINGULAR_CLASS}}Create(name="B"))
        assert len(await svc.get_all()) == 2

    async def test_get_by_id(self, db_session: AsyncSession):
        svc = {{SINGULAR_CLASS}}Service(db_session)
        created = await svc.create({{SINGULAR_CLASS}}Create(name="X"))
        found = await svc.get_by_id(created.id)
        assert found is not None
        assert found.name == "X"
        assert await svc.get_by_id(999) is None

    async def test_update(self, db_session: AsyncSession):
        svc = {{SINGULAR_CLASS}}Service(db_session)
        created = await svc.create({{SINGULAR_CLASS}}Create(name="Old"))
        updated = await svc.update(created.id, {{SINGULAR_CLASS}}Update(name="New"))
        assert updated is not None
        assert updated.name == "New"
        assert await svc.update(999, {{SINGULAR_CLASS}}Update(name="Ghost")) is None

    async def test_delete(self, db_session: AsyncSession):
        svc = {{SINGULAR_CLASS}}Service(db_session)
        created = await svc.create({{SINGULAR_CLASS}}Create(name="Doomed"))
        assert await svc.delete(created.id) is True
        assert await svc.delete(999) is False


class TestAPI:
    async def test_list_empty(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(API)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_crud_roundtrip(self, authenticated_client: httpx.AsyncClient):
        created = await authenticated_client.post(API, json={"name": "Original"})
        assert created.status_code == 201
        item_id = created.json()["id"]

        got = await authenticated_client.get(f"{API}{item_id}")
        assert got.json()["name"] == "Original"

        updated = await authenticated_client.put(f"{API}{item_id}", json={"name": "Updated"})
        assert updated.json()["name"] == "Updated"

        assert (await authenticated_client.delete(f"{API}{item_id}")).status_code == 204
        assert (await authenticated_client.get(f"{API}{item_id}")).status_code == 404

    async def test_missing_item_is_404(self, authenticated_client: httpx.AsyncClient):
        assert (await authenticated_client.get(f"{API}99999")).status_code == 404
        assert (await authenticated_client.delete(f"{API}99999")).status_code == 404

    async def test_create_invalid_data(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(API, json={"name": ""})
        assert resp.status_code == 422

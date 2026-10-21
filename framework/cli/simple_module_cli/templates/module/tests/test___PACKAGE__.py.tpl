"""Tests for the {{MODULE_NAME}} module: schemas, service CRUD, API, boot.

The ``build_test_app``, ``db_session`` and ``authenticated_client`` fixtures
come from the ``simple_module_test`` pytest plugin (registered via
entry_points when that package is installed). No conftest.py is required.
"""

# Import order depends on whether ruff counts this module first-party, which
# differs between an in-repo module and a standalone package; don't fight it.
# ruff: noqa: I001

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError
from simple_module_test import effective_route_paths
from sqlalchemy.ext.asyncio import AsyncSession

from {{PACKAGE_NAME}}.contracts.schemas import (
    {{SINGULAR_CLASS}}Create,
    {{SINGULAR_CLASS}}Update,
)
from {{PACKAGE_NAME}}.module import {{MODULE_NAME}}Module
from {{PACKAGE_NAME}}.service import {{SINGULAR_CLASS}}Service

API = "/api/{{MODULE_SLUG}}/"


class TestMeta:
    def test_meta_name(self):
        assert {{MODULE_NAME}}Module.meta.name == "{{MODULE_NAME}}"

    def test_meta_requires_framework(self):
        assert {{MODULE_NAME}}Module.meta.requires_framework is not None


class TestSchemas:
    def test_create_valid(self):
        data = {{SINGULAR_CLASS}}Create(name="Test")
        assert data.name == "Test"
        assert data.description is None

    def test_create_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            {{SINGULAR_CLASS}}Create(name="")

    def test_update_all_optional(self):
        data = {{SINGULAR_CLASS}}Update()
        assert data.name is None
        assert data.is_active is None


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


class TestBoot:
    async def test_app_boots_with_module(self, build_test_app):
        """Module registers cleanly into a minimal FastAPI host."""
        app = build_test_app({{MODULE_NAME}}Module)
        # effective_route_paths reads the OpenAPI schema: FastAPI >= 0.137
        # includes routers lazily, so ``app.routes`` no longer lists them.
        paths = effective_route_paths(app)
        assert any(p.startswith("/api/{{MODULE_SLUG}}") for p in paths)

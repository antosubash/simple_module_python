"""Template generator for the scaffolded module's test file."""

from __future__ import annotations

from _templates_py import ScaffoldContext


def test_module_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """Tests for the {ctx.class_name} module: service CRUD, API endpoints, schema validation."""

        from __future__ import annotations

        import httpx
        import pytest
        from pydantic import ValidationError
        from {ctx.pkg}.contracts.schemas import (
            {ctx.singular_class}Create,
            {ctx.singular_class}Update,
        )
        from {ctx.pkg}.service import {ctx.singular_class}Service
        from sqlalchemy.ext.asyncio import AsyncSession

        # ── Schema validation ────────────────────────────────────────────────


        class Test{ctx.singular_class}Schemas:
            async def test_create_valid(self):
                data = {ctx.singular_class}Create(name="Test {ctx.singular_class}")
                assert data.name == "Test {ctx.singular_class}"
                assert data.description is None

            async def test_create_empty_name_rejected(self):
                with pytest.raises(ValidationError):
                    {ctx.singular_class}Create(name="")

            async def test_update_all_optional(self):
                data = {ctx.singular_class}Update()
                assert data.name is None
                assert data.is_active is None


        # ── {ctx.singular_class}Service CRUD ──────────────────────────────────────────────


        class Test{ctx.singular_class}Service:
            async def test_create(self, db_session: AsyncSession):
                svc = {ctx.singular_class}Service(db_session)
                item = await svc.create({ctx.singular_class}Create(name="Test"))
                assert item.id is not None
                assert item.name == "Test"
                assert item.is_active is True

            async def test_get_all(self, db_session: AsyncSession):
                svc = {ctx.singular_class}Service(db_session)
                await svc.create({ctx.singular_class}Create(name="A"))
                await svc.create({ctx.singular_class}Create(name="B"))
                items = await svc.get_all()
                assert len(items) == 2

            async def test_get_by_id(self, db_session: AsyncSession):
                svc = {ctx.singular_class}Service(db_session)
                created = await svc.create({ctx.singular_class}Create(name="X"))
                found = await svc.get_by_id(created.id)
                assert found is not None
                assert found.name == "X"

            async def test_get_by_id_not_found(self, db_session: AsyncSession):
                svc = {ctx.singular_class}Service(db_session)
                found = await svc.get_by_id(999)
                assert found is None

            async def test_update(self, db_session: AsyncSession):
                svc = {ctx.singular_class}Service(db_session)
                created = await svc.create({ctx.singular_class}Create(name="Old"))
                updated = await svc.update(created.id, {ctx.singular_class}Update(name="New"))
                assert updated is not None
                assert updated.name == "New"

            async def test_update_not_found(self, db_session: AsyncSession):
                svc = {ctx.singular_class}Service(db_session)
                result = await svc.update(999, {ctx.singular_class}Update(name="Ghost"))
                assert result is None

            async def test_delete(self, db_session: AsyncSession):
                svc = {ctx.singular_class}Service(db_session)
                created = await svc.create({ctx.singular_class}Create(name="Doomed"))
                deleted = await svc.delete(created.id)
                assert deleted is True

            async def test_delete_not_found(self, db_session: AsyncSession):
                svc = {ctx.singular_class}Service(db_session)
                deleted = await svc.delete(999)
                assert deleted is False


        # ── API endpoints ───────────────────────────────────────────────


        class Test{ctx.class_name}API:
            async def test_list_empty(self, authenticated_client: httpx.AsyncClient):
                resp = await authenticated_client.get("/api/{ctx.name}/")
                assert resp.status_code == 200
                assert resp.json() == []

            async def test_create(self, authenticated_client: httpx.AsyncClient):
                resp = await authenticated_client.post(
                    "/api/{ctx.name}/",
                    json={{"name": "Test {ctx.singular_class}"}},
                )
                assert resp.status_code == 201
                data = resp.json()
                assert data["name"] == "Test {ctx.singular_class}"
                assert data["id"] is not None

            async def test_get_by_id(self, authenticated_client: httpx.AsyncClient):
                create_resp = await authenticated_client.post(
                    "/api/{ctx.name}/",
                    json={{"name": "Findable"}},
                )
                item_id = create_resp.json()["id"]
                resp = await authenticated_client.get(f"/api/{ctx.name}/{{item_id}}")
                assert resp.status_code == 200
                assert resp.json()["name"] == "Findable"

            async def test_get_not_found(self, authenticated_client: httpx.AsyncClient):
                resp = await authenticated_client.get("/api/{ctx.name}/99999")
                assert resp.status_code == 404

            async def test_update(self, authenticated_client: httpx.AsyncClient):
                create_resp = await authenticated_client.post(
                    "/api/{ctx.name}/",
                    json={{"name": "Original"}},
                )
                item_id = create_resp.json()["id"]
                resp = await authenticated_client.put(
                    f"/api/{ctx.name}/{{item_id}}",
                    json={{"name": "Updated"}},
                )
                assert resp.status_code == 200
                assert resp.json()["name"] == "Updated"

            async def test_delete(self, authenticated_client: httpx.AsyncClient):
                create_resp = await authenticated_client.post(
                    "/api/{ctx.name}/",
                    json={{"name": "Deletable"}},
                )
                item_id = create_resp.json()["id"]
                resp = await authenticated_client.delete(f"/api/{ctx.name}/{{item_id}}")
                assert resp.status_code == 204

            async def test_delete_not_found(self, authenticated_client: httpx.AsyncClient):
                resp = await authenticated_client.delete("/api/{ctx.name}/99999")
                assert resp.status_code == 404

            async def test_create_invalid_data(self, authenticated_client: httpx.AsyncClient):
                resp = await authenticated_client.post(
                    "/api/{ctx.name}/",
                    json={{"name": ""}},
                )
                assert resp.status_code == 422


        # ── Module lifecycle ────────────────────────────────────────────────


        class Test{ctx.class_name}ModuleLifecycle:
            async def test_on_startup_does_not_call_create_all(self):
                """on_startup should not create tables — Alembic manages schema."""
                from unittest.mock import AsyncMock, MagicMock

                from {ctx.pkg}.module import {ctx.class_name}Module

                mod = {ctx.class_name}Module()
                mock_app = MagicMock()
                mock_app.state.db.engine = AsyncMock()

                await mod.on_startup(mock_app)

                mock_app.state.db.engine.begin.assert_not_called()
        '''

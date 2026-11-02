"""File storage with no tenant bound: single-tenant installs, and strict fail-closed.

A host with ``multi_tenant`` off binds no tenant; uploads must keep working and
land in ``DEFAULT_TENANT_ID`` (the same value the adoption migration
back-filled). With ``multi_tenant`` on, a caller that has no organisation is
refused *before* any bytes are written, so a failed upload leaves no orphan.
"""

from __future__ import annotations

import pytest
from file_storage import constants
from file_storage.models import StoredFile
from simple_module_db import DEFAULT_TENANT_ID, MissingTenantError
from simple_module_hosting.settings import Settings
from simple_module_test.database import database_url_for_tests
from sqlalchemy import select

API = constants.ROUTE_PREFIX_API


class TestSingleTenantInstall:
    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            database_url=database_url_for_tests(),
            environment="testing",
            secret_key="test-secret-key",
            multi_tenant=False,
            auth_provider="users",
        )

    async def test_upload_is_stamped_with_the_default_tenant(self, app, authenticated_client):
        resp = await authenticated_client.post(
            f"{API}/upload", files={"file": ("a.txt", b"hi", "text/plain")}
        )

        assert resp.status_code == 201, resp.text
        out = resp.json()
        assert out["key"].startswith(f"{DEFAULT_TENANT_ID}/")
        async with app.state.sm.db.session_factory() as session:
            row = (await session.execute(select(StoredFile))).scalar_one()
        assert row.tenant_id == DEFAULT_TENANT_ID

        download = await authenticated_client.get(f"{API}/files/{out['id']}/download")
        assert download.status_code == 200
        assert download.content == b"hi"
        listed = (await authenticated_client.get(f"{API}/files")).json()
        assert listed["total"] == 1

    async def test_rows_from_any_tenant_stay_visible(self, app, authenticated_client):
        """Unbound reads are not narrowed to the default tenant: a row written
        while ``multi_tenant`` was briefly on is still the install's."""
        async with app.state.sm.db.session_factory() as session:
            session.add(
                StoredFile(
                    tenant_id="was-a-tenant",
                    key="old/key.txt",
                    filename="old.txt",
                    content_type="text/plain",
                    size_bytes=1,
                    backend=constants.BackendId.FILESYSTEM,
                    checksum_sha256="0" * 64,
                )
            )
            await session.commit()

        listed = (await authenticated_client.get(f"{API}/files")).json()

        assert [f["filename"] for f in listed["items"]] == ["old.txt"]


class TestStrictWithNoTenant:
    async def test_upload_fails_closed_before_writing_bytes(self, app):
        """No tenant bound under strict mode: refused, and nothing stored —
        the owner is settled before the backend sees a byte."""
        from io import BytesIO

        from fastapi import UploadFile
        from file_storage.service import FileStorageService

        services = app.state.file_storage
        written: list[str] = []
        original_put = services.backend.put

        async def spy_put(key, *args, **kwargs):
            written.append(key)
            return await original_put(key, *args, **kwargs)

        services.backend.put = spy_put
        try:
            async with app.state.sm.db.session_factory() as session:
                service = FileStorageService(session, services.backend, services.settings)
                with pytest.raises(MissingTenantError):
                    await service.upload(UploadFile(BytesIO(b"hi"), filename="a.txt"))
        finally:
            services.backend.put = original_put

        assert written == []

    async def test_service_reads_raise_without_a_tenant(self, app):
        from file_storage.service import FileStorageService

        services = app.state.file_storage
        async with app.state.sm.db.session_factory() as session:
            service = FileStorageService(session, services.backend, services.settings)
            with pytest.raises(MissingTenantError):
                await service.list_files()

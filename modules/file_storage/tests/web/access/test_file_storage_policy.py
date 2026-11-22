"""Generic routes enforce module-owned file policies, including side channels (#999)."""

from __future__ import annotations

import uuid

import pytest
from file_storage.contracts import StoredFile
from simple_module_core.access.file_access import register_file_access_policy
from simple_module_core.access.resources import ACTION_VIEW
from simple_module_db import tenant_context
from simple_module_db.resource_policy import OwnedResourcePolicy

API = "/api/file-storage"
TAG = "guides.licence"
REVIEW = "guides.review"


@pytest.fixture
async def licence(app, storage, tenant_client):
    # A module can register from register_settings using only the core API.
    policy = OwnedResourcePolicy(StoredFile.created_by, bypass_perm=REVIEW)
    register_file_access_policy(app, TAG, policy, publishable=False)
    async with tenant_client("member") as uploader:
        resp = await uploader.client.post(
            f"{API}/upload", files={"file": ("licence.pdf", b"private licence", "application/pdf")}
        )
        assert resp.status_code == 201, resp.text
        file_id = resp.json()["id"]
        with tenant_context(uploader.tenant_id):
            async with app.state.sm.db.session_factory() as db:
                row = await db.get(StoredFile, uuid.UUID(file_id))
                row.owner_module = TAG
                await db.commit()
        yield uploader, file_id


async def test_uploader_reads_but_cannot_publish(licence):
    uploader, file_id = licence
    assert (await uploader.client.get(f"{API}/files/{file_id}")).status_code == 200
    download = await uploader.client.get(f"{API}/files/{file_id}/download")
    assert download.content == b"private licence"
    patch = await uploader.client.patch(f"{API}/files/{file_id}", json={"public": True})
    assert patch.status_code == 403


async def test_policy_permission_adds_access_without_manage(app, licence, tenant_client):
    uploader, file_id = licence
    app.state.sm.permissions.map_role("tenant:member", [REVIEW])
    async with tenant_client("member", tenant_id=uploader.tenant_id) as reviewer:
        resp = await reviewer.client.get(f"{API}/files/{file_id}")
        assert resp.status_code == 200, resp.text
        listing = (await reviewer.client.get(f"{API}/files")).json()
        assert listing["total"] == 1
        assert [r["id"] for r in listing["items"]] == [file_id]


async def test_manager_cannot_bypass_module_policy(licence, tenant_client):
    uploader, file_id = licence
    async with tenant_client("owner", tenant_id=uploader.tenant_id) as stranger:
        for suffix in ("", "/download", "/thumbnail"):
            resp = await stranger.client.get(f"{API}/files/{file_id}{suffix}")
            assert resp.status_code == 404
        patch = await stranger.client.patch(f"{API}/files/{file_id}", json={"public": True})
        assert patch.status_code == 404
        assert (await stranger.client.delete(f"{API}/files/{file_id}")).status_code == 404
        listing = (await stranger.client.get(f"{API}/files")).json()
        assert listing["items"] == [] and listing["total"] == 0
        bulk = await stranger.client.post(f"{API}/files/bulk-delete", json={"ids": [file_id]})
        assert bulk.json() == {"deleted": 0, "ids": []}
        browse = await stranger.client.get("/file-storage/", headers={"X-Inertia": "true"})
        props = browse.json()["props"]
        assert props["files"] == []
        assert props["pagination"]["total"] == 0
        assert props["content_types"] == props["uploaders"] == []
        assert props["used_bytes"] == 0


async def test_never_public_even_if_flag_already_true(app, licence, client):
    uploader, file_id = licence
    with tenant_context(uploader.tenant_id):
        async with app.state.sm.db.session_factory() as db:
            row = await db.get(StoredFile, uuid.UUID(file_id))
            row.public = True
            await db.commit()
    for suffix in ("", "/licence.pdf", "/thumbnail"):
        assert (await client.get(f"{API}/public/{file_id}{suffix}")).status_code == 404
    resp = await uploader.client.patch(f"{API}/files/{file_id}", json={"public": False})
    assert resp.status_code == 200


async def test_permission_never_crosses_tenant_boundary(app, licence, tenant_client):
    _, file_id = licence
    app.state.sm.permissions.map_role("tenant:owner", [REVIEW])
    async with tenant_client() as other:
        assert (await other.client.get(f"{API}/files/{file_id}")).status_code == 404
        assert (await other.client.get(f"{API}/files")).json()["total"] == 0


async def test_delete_uses_action_filter_fallback(app, licence, tenant_client):
    uploader, file_id = licence

    class ReadOnly:
        def filter(self, principal, action, stmt):
            return stmt if action == ACTION_VIEW else stmt.where(False)

        def can(self, principal, action, obj):
            return False

    # Distinct tag to avoid duplicate registration.
    register_file_access_policy(app, "guides.readonly", ReadOnly(), publishable=False)
    with tenant_context(uploader.tenant_id):
        async with app.state.sm.db.session_factory() as db:
            row = await db.get(StoredFile, uuid.UUID(file_id))
            row.owner_module = "guides.readonly"
            await db.commit()
    async with tenant_client("owner", tenant_id=uploader.tenant_id) as reader:
        assert (await reader.client.get(f"{API}/files/{file_id}")).status_code == 200
        assert (await reader.client.delete(f"{API}/files/{file_id}")).status_code == 403
        bulk = await reader.client.post(f"{API}/files/bulk-delete", json={"ids": [file_id]})
        assert bulk.json() == {"deleted": 0, "ids": []}


async def test_completed_upload_session_hides_a_now_invisible_file(app, licence):
    from datetime import UTC, datetime, timedelta

    from file_storage.models import UploadSession

    uploader, file_id = licence
    with tenant_context(uploader.tenant_id):
        async with app.state.sm.db.session_factory() as db:
            row = await db.get(StoredFile, uuid.UUID(file_id))
            session = UploadSession(
                tenant_id=uploader.tenant_id,
                created_by=uploader.user_id,
                key=row.key,
                filename=row.filename,
                content_type=row.content_type,
                total_size=row.size_bytes,
                part_size=5,
                backend_upload_id="finished",
                status="completed",
                file_id=row.id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            db.add(session)
            row.owner_module = "missing.policy"
            await db.commit()
            upload_id = str(session.id)
    resp = await uploader.client.get(f"{API}/uploads/{upload_id}")
    assert resp.status_code == 404
    retry = await uploader.client.post(f"{API}/uploads/{upload_id}/complete", json={"parts": []})
    assert retry.status_code == 404


async def test_service_upload_sets_owner_tag_and_refuses_public_before_writing(
    app, licence, storage
):
    from io import BytesIO

    from fastapi import UploadFile
    from file_storage.files.service import FileStorageService
    from simple_module_core.access.file_access import file_access_policies
    from simple_module_core.access.permission_denied import PermissionDenied

    uploader, _ = licence
    with tenant_context(uploader.tenant_id):
        async with app.state.sm.db.session_factory() as db:
            service = FileStorageService(
                db, storage.backend, storage.settings, policies=file_access_policies(app)
            )
            out = await service.upload(
                UploadFile(BytesIO(b"licence"), filename="new.pdf"), owner_module=TAG
            )
            row = await db.get(StoredFile, out.id)
            assert row.owner_module == TAG
            before = list(storage.backend.root.rglob("*"))
            with pytest.raises(PermissionDenied):
                await service.upload(
                    UploadFile(BytesIO(b"never public"), filename="no.pdf"),
                    owner_module=TAG,
                    public=True,
                )
            assert list(storage.backend.root.rglob("*")) == before


async def test_bound_upload_honors_publish_action(app, licence, storage):
    from io import BytesIO

    from fastapi import UploadFile
    from file_storage.files.service import FileStorageService
    from simple_module_core.access.file_access import file_access_policies
    from simple_module_core.access.permission_denied import PermissionDenied
    from simple_module_core.access.resources import ResourcePrincipal

    class ReadOnly:
        def filter(self, principal, action, stmt):
            return stmt if action == ACTION_VIEW else stmt.where(False)

        def can(self, principal, action, obj):
            return False

    register_file_access_policy(app, "guides.upload", ReadOnly())
    uploader, _ = licence
    with tenant_context(uploader.tenant_id):
        async with app.state.sm.db.session_factory() as db:
            service = FileStorageService(
                db,
                storage.backend,
                storage.settings,
                policies=file_access_policies(app),
                principal=ResourcePrincipal(uploader.user_id),
            )
            with pytest.raises(PermissionDenied):
                await service.upload(
                    UploadFile(BytesIO(b"private"), filename="no.pdf"),
                    owner_module="guides.upload",
                    public=True,
                )

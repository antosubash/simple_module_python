"""Public originals and thumbnails deny orphan files before teardown delivery."""

import io

import pytest
from file_storage import constants
from PIL import Image
from simple_module_core.tenant_events import TENANT_DELETED_CHANNEL
from sqlalchemy import delete
from tenants.models import Invitation, Membership, Tenant


@pytest.mark.parametrize("directory", [True, False], ids=["with-directory", "without-directory"])
async def test_file_storage_public_checks_deleted_tenant(
    app, authenticated_client, client, admin_tenant_id, directory, monkeypatch
):
    content = io.BytesIO()
    Image.new("RGB", (20, 20)).save(content, format="PNG")
    response = await authenticated_client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files={"file": ("image.png", content.getvalue(), "image/png")},
        data={"public": "true"},
    )
    assert response.status_code == 201, response.text
    file = response.json()
    urls = [
        file["public_url"],
        f"{constants.ROUTE_PREFIX_API}/public/{file['id']}",
        f"{constants.ROUTE_PREFIX_API}/public/{file['id']}/thumbnail?w=64",
    ]
    from file_storage.service import FileStorageService

    original_get_public = FileStorageService.get_public
    original_lookup = app.state.tenant_exists
    request_sessions = []

    async def get_public(service, file_id):
        row = await original_get_public(service, file_id)
        assert service.db.in_transaction()
        request_sessions.append(service.db)
        return row

    async def lookup(tenant_id):
        assert not request_sessions[-1].in_transaction()
        return await original_lookup(tenant_id)

    monkeypatch.setattr(FileStorageService, "get_public", get_public)
    monkeypatch.setattr(app.state, "tenant_exists", lookup)
    monkeypatch.setattr("file_storage.tenant_cache.TENANT_EXISTS_TTL_SECONDS", 0)
    for url in urls:
        assert (await client.get(url)).status_code == 200
        assert not request_sessions[-1].in_transaction()

    # Bypass the deletion publisher to leave the rows/bytes in place: the
    # immediate guard must work even while the outbox worker is unavailable.
    async with app.state.sm.db.session_factory() as db:
        for model in (Membership, Invitation):
            await db.execute(delete(model).where(model.tenant_id == admin_tenant_id))
        await db.execute(delete(Tenant).where(Tenant.id == admin_tenant_id))
        await db.commit()

    # A missed event is bounded by the TTL; expire the previously cached answer.
    monkeypatch.setattr("file_storage.tenant_cache.TENANT_EXISTS_TTL_SECONDS", 0)
    if not directory:
        # Hosts without a tenant registry retain the single-tenant contract.
        monkeypatch.delattr(app.state, "tenant_exists")
    for url in urls:
        response = await client.get(url, headers={"If-None-Match": '"cached"'})
        assert response.status_code == (404 if directory else 200), response.text


async def test_tenant_existence_cache_hit_invalidation_and_ttl(monkeypatch):
    from unittest.mock import AsyncMock

    from fastapi import FastAPI
    from file_storage.tenant_cache import cached_tenant_exists
    from simple_module_core.invalidation import InvalidationBus

    app = FastAPI()
    bus = InvalidationBus()
    from file_storage.module import FileStorageModule

    FileStorageModule().register_invalidations(bus, app)
    lookup = AsyncMock(return_value=True)
    app.state.tenant_exists = lookup
    assert await cached_tenant_exists(app, "tenant") is True
    assert await cached_tenant_exists(app, "tenant") is True
    assert lookup.await_count == 1
    lookup.return_value = False
    await bus.publish(TENANT_DELETED_CHANNEL, key="tenant")
    assert await cached_tenant_exists(app, "tenant") is False
    assert lookup.await_count == 2
    monkeypatch.setattr("file_storage.tenant_cache.TENANT_EXISTS_TTL_SECONDS", 0)
    assert await cached_tenant_exists(app, "tenant") is False
    assert lookup.await_count == 3

"""The reaper commits the soft-delete before it drops the backend object (#396).

Also: the tenant-branding in-flight read map is per app and its failures are
always retrieved.
"""

from __future__ import annotations

import asyncio
import gc

from branding import reaper, tenant_branding
from branding.tenant_branding import TenantCache
from file_storage.models import StoredFile
from settings.contracts.schemas import SettingScope
from settings.service import SettingService
from simple_module_db import all_tenants
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


async def _upload_then_unset(app, a) -> str:
    resp = await a.client.post(
        "/api/branding/tenant/logo", files={"file": ("l.png", _PNG, "image/png")}
    )
    assert resp.status_code == 200, resp.text
    async with app.state.sm.db.session_factory() as db:
        service = SettingService(db)
        row = await service.get_scoped(SettingScope.TENANT, a.tenant_id, "branding.logo_file_id")
        file_id = row.value
        await service.delete_scoped(SettingScope.TENANT, a.tenant_id, "branding.logo_file_id")
        await db.commit()
    return file_id


async def _row(app, file_id: str) -> StoredFile:
    with all_tenants():
        async with app.state.sm.db.session_factory() as db:
            stmt = select(StoredFile).execution_options(include_deleted=True)
            return next(r for r in (await db.execute(stmt)).scalars() if str(r.id) == file_id)


async def test_failed_commit_keeps_the_bytes(app, tenant_client, monkeypatch):
    async with tenant_client() as a:
        file_id = await _upload_then_unset(app, a)
        key = (await _row(app, file_id)).key
        backend = app.state.file_storage.backend

        async def boom(self):
            raise RuntimeError("commit failed")

        monkeypatch.setattr(AsyncSession, "commit", boom)
        await reaper.reap(app, file_id, tenant_id=a.tenant_id)  # logs, never raises
        monkeypatch.undo()

        assert (await _row(app, file_id)).is_deleted is False
        assert await backend.exists(key)


async def test_bytes_are_dropped_only_after_the_commit(app, tenant_client, monkeypatch):
    events: list[str] = []
    orig_commit = AsyncSession.commit

    async def commit(self):
        events.append("commit")
        await orig_commit(self)

    async with tenant_client() as a:
        file_id = await _upload_then_unset(app, a)
        backend = app.state.file_storage.backend
        orig_delete = backend.delete

        async def delete(key):
            events.append("delete")
            await orig_delete(key)

        monkeypatch.setattr(AsyncSession, "commit", commit)
        monkeypatch.setattr(backend, "delete", delete)
        await reaper.reap(app, file_id, tenant_id=a.tenant_id)

    # The original and any cached thumbnail variants: every delete after the commit.
    assert events[0] == "commit" and "delete" in events
    assert set(events[1:]) == {"delete"}
    assert (await _row(app, file_id)).is_deleted is True


async def test_failed_unawaited_read_is_still_retrieved(app, monkeypatch):
    cache = TenantCache()
    started = asyncio.Event()

    async def boom(_app, _tid):
        started.set()
        raise RuntimeError("read failed")

    monkeypatch.setattr(tenant_branding, "read_overrides", boom)
    entry = tenant_branding._shared_read(app, cache, "t1")
    await started.wait()
    await asyncio.sleep(0)
    assert entry[1].done()
    assert cache.inflight == {}

    seen: list[dict] = []
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(lambda _l, ctx: seen.append(ctx))
    try:
        del entry
        gc.collect()
        assert not seen
    finally:
        loop.set_exception_handler(None)

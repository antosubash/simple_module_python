"""Quota admission serializes independent file-DB connections (#753)."""

import asyncio
from io import BytesIO
from sqlite3 import SQLITE_BUSY_SNAPSHOT

import pytest
from fastapi import UploadFile
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.models import Base, StoredFile, UploadSession
from file_storage.service import FileStorageService
from file_storage.settings import FileStorageSettings
from file_storage.upload_support import QuotaExceededError
from file_storage.uploads import UploadSessionService
from simple_module_db import tenant_context
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from sqlalchemy import event, func, select, text


@pytest.mark.parametrize("reservation", [False, True])
@pytest.mark.parametrize("snapshot", [False, True])
async def test_concurrent_storage_admission_stays_within_quota(tmp_path, reservation, snapshot):
    url = f"sqlite+aiosqlite:///{tmp_path}/quota.db"
    first, second = init_db(url), init_db(url)
    for state in (first, second):
        state.tenant_strict = True
        register_listeners(state)
    backend = FilesystemBackend(root=tmp_path / "files")
    config = FileStorageSettings(quota_bytes=10)
    writing = asyncio.Event()

    @event.listens_for(second.engine.sync_engine, "before_cursor_execute")
    def attempted_write(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE")):
            writing.set()

    async def admit(db):
        files = FileStorageService(db, backend, config)
        if reservation:
            return await UploadSessionService(files).create(
                filename="file.bin", content_type="application/octet-stream", total_size=8
            )
        return await files.upload(UploadFile(BytesIO(b"12345678"), filename="file.bin"))

    try:
        async with first.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with first.session_factory() as a, second.session_factory() as b:
            with tenant_context("tenant-a"):
                if snapshot:
                    await b.execute(text("BEGIN"))
                    await b.scalar(select(func.count()).select_from(StoredFile))
                await admit(a)
                if snapshot:
                    await a.commit()

                async def contender():
                    try:
                        await admit(b)
                        await b.commit()
                    except QuotaExceededError as exc:
                        if snapshot:
                            assert exc.__cause__.orig.sqlite_errorcode == SQLITE_BUSY_SNAPSHOT
                        await b.rollback()
                        return "refused"
                    return "admitted"

                task = asyncio.create_task(contender())
                try:
                    await asyncio.wait_for(writing.wait(), 5)
                    await a.commit()
                    assert await asyncio.wait_for(task, 5) == "refused"
                finally:
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                model, size = (
                    (UploadSession, UploadSession.total_size)
                    if reservation
                    else (StoredFile, StoredFile.size_bytes)
                )
                assert await b.scalar(select(func.sum(size)).select_from(model)) == 8
                if not reservation:
                    assert len(list((tmp_path / "files").rglob("*.bin"))) == 1
    finally:
        await first.engine.dispose()
        await second.engine.dispose()

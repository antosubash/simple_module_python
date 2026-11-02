"""The object janitor removes rolled-back uploads and retries failed deletes."""

import asyncio
import os
import uuid
from datetime import timedelta

from background_tasks import sync_db
from file_storage import tasks
from file_storage.models import StoredFile
from file_storage.object_reaper import reap_objects
from simple_module_db import tenant_context
from test_file_storage_upload_tasks import worker  # noqa: F401


def test_reconcile_spares_live_recent_and_foreign_objects(worker):  # noqa: F811
    keys = [f"tenant-a/2026/10/15/{uuid.uuid4().hex}.bin" for _ in range(4)]
    keys.append("foreign-app/export.bin")

    async def store():
        for key in keys:

            async def body():
                yield b"bytes"

            await worker.put(key, body(), content_type="x/y", size=5)
            if key != keys[3]:
                os.utime(worker._resolve(key), (1, 1))

    asyncio.run(store())
    with sync_db.sync_session() as db, tenant_context("tenant-a"):
        for key, deleted in [(keys[0], False), (keys[1], True)]:
            db.add(
                StoredFile(
                    key=key,
                    filename="a",
                    content_type="x/y",
                    size_bytes=5,
                    backend=worker.backend_id,
                    tenant_id="tenant-a",
                    is_deleted=deleted,
                )
            )
    # keys[2] has no committed row, as after an upload commit failure.
    assert tasks.reap_objects() == 2
    assert [worker._resolve(key).exists() for key in keys] == [True, False, False, True, True]
    assert asyncio.run(reap_objects(worker, sync_db.sync_session, grace=timedelta(hours=1))) == 0

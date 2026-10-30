"""Synchronous, tenant-scoped file access for workers (#708).

Uses the background-tasks calling thread's persistent loop and session factory;
imports of this module are deferred by the public contracts package.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO
from uuid import UUID

from background_tasks.outbox_loop import run_on_worker_loop
from background_tasks.outbox_worker import worker_bus, worker_session_factory
from fastapi import UploadFile
from simple_module_db import independent_session
from simple_module_db.callbacks import register_on_commit
from starlette.datastructures import Headers

from file_storage.backend_guard import require_backend
from file_storage.contracts import FileUploaded, NotSupportedError, StoredFileOut
from file_storage.downloads import presigned_download_url
from file_storage.models import StoredFile
from file_storage.scope import owning_tenant
from file_storage.service import FileStorageService
from file_storage.worker_support import backend_and_settings

logger = logging.getLogger(__name__)


def store_path(
    source: str | os.PathLike[str] | BinaryIO,
    *,
    filename: str | None = None,
    content_type: str = "application/octet-stream",
    public: bool = False,
) -> StoredFileOut:
    """Store a path or the remaining bytes of a caller-owned stream.

    Anonymous streams require ``filename``. Caller-owned streams stay open.
    The independent transaction commits before this function returns.
    """
    backend, settings = backend_and_settings()
    factory = worker_session_factory()
    bus = worker_bus()

    async def store() -> StoredFileOut:
        out = None
        committed = False

        def mark_committed() -> None:
            nonlocal committed
            committed = True

        try:
            async with independent_session(factory) as db:
                owning_tenant(db)  # Fail closed before even opening the source path.
                service = FileStorageService(db, backend, settings)
                with _source(source, filename) as (handle, name):
                    upload = UploadFile(
                        handle, filename=name, headers=Headers({"content-type": content_type})
                    )
                    out = await service.upload(upload, public=public)
                register_on_commit(db, mark_committed)
                register_on_commit(
                    db,
                    partial(
                        bus.publish,
                        FileUploaded(
                            file_id=out.id,
                            key=out.key,
                            backend=out.backend,
                            size_bytes=out.size_bytes,
                            uploaded_by=out.uploaded_by,
                        ),
                    ),
                )
            return out
        except BaseException:
            if out is not None and not committed:
                await _compensate(factory, backend, out)
            raise

    return run_on_worker_loop(store)


async def _compensate(factory, backend, out: StoredFileOut) -> None:
    # A lost COMMIT acknowledgement is ambiguous: never delete a durable file.
    try:
        async with factory() as db:
            # Trashed rows keep their object for restore: only a missing row means rollback.
            row = await db.get(StoredFile, out.id, execution_options={"include_deleted": True})
    except BaseException:
        logger.exception("file_storage.worker_commit_check_failed key=%s", out.key)
        return
    if row is None:
        try:
            await backend.delete(out.key)
        except BaseException:
            logger.exception("file_storage.worker_cleanup_failed key=%s", out.key)


@contextmanager
def _source(source, filename) -> Generator[tuple[BinaryIO, str]]:
    if isinstance(source, (str, os.PathLike)):
        path = Path(source)
        with path.open("rb") as handle:
            yield handle, filename or path.name
    else:
        name = filename or getattr(source, "name", None)
        if not isinstance(name, (str, os.PathLike)) or not os.fspath(name):
            raise ValueError("filename is required for anonymous streams")
        yield source, filename or Path(name).name


def _reader(file_id: UUID):
    backend, settings = backend_and_settings()
    factory = worker_session_factory()

    async def metadata():
        async with factory() as db:
            service = FileStorageService(db, backend, settings)
            row = await service.get(file_id)
            require_backend(backend, row)
            return row

    # Metadata is detached and its transaction closed before any streaming.
    return backend, settings, run_on_worker_loop(metadata)


@contextmanager
def open_local(file_id: UUID) -> Generator[Path]:
    """Download into a private temporary directory, removed on every exit."""
    backend, _, row = _reader(file_id)
    with TemporaryDirectory(prefix="sm-file-") as directory:
        path = Path(directory) / ("file" + Path(row.filename).suffix)

        async def download() -> None:
            body = await backend.get(row.key)
            try:
                with path.open("wb") as handle:
                    async for chunk in body:
                        handle.write(chunk)
            finally:
                close = getattr(body, "aclose", None)
                if close is not None:
                    await close()

        run_on_worker_loop(download)
        yield path


def presigned_url(file_id: UUID, *, ttl_seconds: int | None = None) -> str:
    """Sign a scoped file download, or raise ``NotSupportedError``."""
    backend, settings, row = _reader(file_id)
    if not backend.supports_presigned_url:
        raise NotSupportedError("The configured backend cannot presign downloads")
    ttl = settings.s3_presign_ttl_seconds if ttl_seconds is None else ttl_seconds
    if ttl <= 0:
        raise ValueError("ttl_seconds must be positive")
    return run_on_worker_loop(lambda: presigned_download_url(backend, row, ttl, attachment=True))

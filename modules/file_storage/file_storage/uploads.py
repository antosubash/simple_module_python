"""Resumable multipart upload sessions (#454).

A browser uploading a multi-GB file cannot do it in one request: a dropped
connection loses everything, and a proxy's body limit refuses it outright. A
session splits the file into parts the client sends (straight to S3, or through
the app for the filesystem) and can resume after a reload. The backend's own
part listing is the truth about what arrived; the ``UploadSession`` row records
only what was promised — key, size, owner, deadline.

Reuses the one-shot upload's rules (content type, tenant-prefixed key, owning
tenant, compensation on DB failure) so a file that arrives this way is
indistinguishable from one posted to ``/upload`` — except that nothing hashed
it on the way through, so its checksum starts null.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from simple_module_db.listeners import current_user_id
from sqlalchemy import select

from file_storage import constants, queries
from file_storage.contracts.schemas import StoredFileOut
from file_storage.contracts.service import (
    NotSupportedError,
    Part,
    StorageNotFoundError,
)
from file_storage.models import StoredFile, UploadSession
from file_storage.scope import owning_tenant
from file_storage.service import FileStorageService, FileTooLargeError, generate_key
from file_storage.upload_guards import UploadGuards
from file_storage.upload_support import (
    InvalidPartError,
    PartsMismatchError,
    QuotaExceededError,
    SizeMismatchError,
    UploadClosedError,
    UploadNotFoundError,
    choose_part_size,
    expected_part_size,
    part_path,
    total_parts,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _etag(value: str) -> str:
    return value.strip('"')


class UploadSessionService(UploadGuards):
    """Creates, resumes, completes and aborts a user's upload sessions."""

    def __init__(self, files: FileStorageService) -> None:
        self.files = files
        self.db: AsyncSession = files.db
        self.settings = files.settings

    # ── Lifecycle ────────────────────────────────────────────────────

    async def create(
        self, *, filename: str, content_type: str, total_size: int, public: bool = False
    ) -> UploadSession:
        backend = self.backend
        self.files._check_content_type(content_type)
        if total_size > self.settings.max_direct_upload_bytes:
            raise FileTooLargeError(
                f"Upload exceeds {self.settings.max_direct_upload_bytes} bytes."
            )
        tenant_id = owning_tenant(self.db)
        # Housekeeping that needs no worker: without background_tasks nothing
        # else ever reaps, so a user's abandoned uploads go when they start one.
        # Done first so their reservations stop counting against the quota.
        await self.abort_expired(owner=current_user_id.get())
        await self._check_quota(total_size, reserve=True)

        key = generate_key(tenant_id, filename)
        upload_id = await backend.create_multipart(key, content_type)
        try:
            session = UploadSession(
                tenant_id=tenant_id,
                key=key,
                filename=filename,
                content_type=content_type,
                total_size=total_size,
                part_size=choose_part_size(total_size, self.settings.multipart_part_size_bytes),
                backend_upload_id=upload_id,
                public=public,
                expires_at=datetime.now(UTC)
                + timedelta(seconds=self.settings.upload_session_ttl_seconds),
            )
            self.db.add(session)
            await self.db.flush()
        except Exception:
            await self._abort_backend(key, upload_id)
            raise
        return session

    async def get(self, upload_id: uuid.UUID) -> UploadSession:
        """The caller's own session. Others' ids miss exactly like unknown ones."""
        owner = current_user_id.get()
        stmt = select(UploadSession).where(
            UploadSession.id == upload_id, UploadSession.created_by == owner
        )
        session = (await self.db.execute(stmt)).scalar_one_or_none() if owner else None
        if session is None:
            raise UploadNotFoundError(str(upload_id))
        return session

    async def get_open(self, upload_id: uuid.UUID) -> UploadSession:
        """:meth:`get`, refusing a finished or expired session."""
        session = await self.get(upload_id)
        if session.status != constants.UploadStatus.ACTIVE:
            raise UploadClosedError(session.status)
        if session.expires_at <= datetime.now(UTC):
            await self.abort(session)
            raise UploadClosedError(constants.UploadStatus.ABORTED)
        return session

    async def parts(self, session: UploadSession) -> list[Part]:
        if session.status != constants.UploadStatus.ACTIVE:
            return []
        try:
            return await self.backend.list_parts(session.key, session.backend_upload_id)
        except StorageNotFoundError:
            return []

    async def abort(self, session: UploadSession) -> None:
        if session.status == constants.UploadStatus.ACTIVE:
            await self._abort_backend(session.key, session.backend_upload_id)
            session.status = constants.UploadStatus.ABORTED
            await self.db.flush()

    async def abort_expired(self, *, owner: str | None) -> int:
        """Abort ``owner``'s sessions past their deadline; how many went."""
        if not owner:
            return 0
        stmt = select(UploadSession).where(
            UploadSession.created_by == owner,
            UploadSession.status == constants.UploadStatus.ACTIVE,
            UploadSession.expires_at <= datetime.now(UTC),
        )
        expired = list((await self.db.execute(stmt)).scalars())
        for session in expired:
            await self.abort(session)
        return len(expired)

    # ── Parts ────────────────────────────────────────────────────────

    def _check_part_no(self, session: UploadSession, part_no: int) -> None:
        if not 1 <= part_no <= total_parts(session):
            raise InvalidPartError(f"part {part_no} outside 1..{total_parts(session)}")

    async def part_urls(
        self, session: UploadSession, numbers: list[int]
    ) -> tuple[dict[int, str], bool]:
        """``({part: url}, direct)``; ``direct`` is false when parts go through the app."""
        for number in numbers:
            self._check_part_no(session, number)
        ttl = self.settings.s3_presign_ttl_seconds
        try:
            return {
                n: await self.backend.presign_part(
                    session.key, session.backend_upload_id, n, ttl, expected_part_size(session, n)
                )
                for n in numbers
            }, True
        except NotSupportedError:
            return {n: part_path(session.id, n) for n in numbers}, False

    async def write_part(
        self, session: UploadSession, part_no: int, body: AsyncIterator[bytes]
    ) -> Part:
        """Relay one part through the app (backends that cannot presign)."""
        self._check_part_no(session, part_no)
        limit = expected_part_size(session, part_no)
        seen = 0

        async def _bounded() -> AsyncIterator[bytes]:
            nonlocal seen
            async for chunk in body:
                seen += len(chunk)
                if seen > limit:
                    raise InvalidPartError(f"part {part_no} exceeds {limit} bytes")
                yield chunk

        part = await self.backend.write_part(
            session.key, session.backend_upload_id, part_no, _bounded(), max_bytes=limit
        )
        if part.size != limit:
            raise InvalidPartError(f"part {part_no} is {part.size} bytes, expected {limit}")
        return part

    # ── Completion ───────────────────────────────────────────────────

    async def complete(
        self, session: UploadSession, claimed: dict[int, str]
    ) -> tuple[StoredFileOut, bool]:
        """Assemble the object and record the file; ``(file, created)``.

        ``created`` is false when a retried request finds the session already
        completed, so the caller does not publish ``FileUploaded`` twice.
        """
        if session.status == constants.UploadStatus.COMPLETED and session.file_id:
            existing = await self.files.get(session.file_id)
            return StoredFileOut.model_validate(queries.to_out_dict(existing)), False
        session = await self.get_open(session.id)

        backend = self.backend
        held = {p.no: p for p in await self.parts(session)}
        wanted = range(1, total_parts(session) + 1)
        missing = [n for n in wanted if n not in held]
        mismatched = [
            n for n, etag in claimed.items() if n in held and _etag(held[n].etag) != _etag(etag)
        ] + [n for n in wanted if n in held and held[n].size != expected_part_size(session, n)]
        if missing or mismatched or set(held) - set(wanted):
            raise PartsMismatchError(missing, sorted(set(mismatched)))

        await backend.complete_multipart(
            session.key, session.backend_upload_id, [held[n] for n in wanted]
        )
        info = await backend.head(session.key)
        if info.size != session.total_size:
            await self._reject(session)
            raise SizeMismatchError(session.total_size, info.size)
        # The declared size is only a claim; the stored object is the fact. Limits
        # are re-checked against it, in the transaction that records the file.
        max_bytes = self.settings.max_direct_upload_bytes
        if info.size > max_bytes:
            await self._reject(session)
            raise FileTooLargeError(f"Upload exceeds {max_bytes} bytes.")
        try:
            await self._check_quota(info.size, reserve=False)
        except QuotaExceededError:
            await self._reject(session)
            raise

        try:
            row = StoredFile(
                tenant_id=session.tenant_id,
                key=session.key,
                filename=session.filename,
                content_type=session.content_type,
                size_bytes=info.size,
                backend=self.files.backend.backend_id,
                checksum_sha256=None,
                public=session.public,
            )
            self.db.add(row)
            await self.db.flush()
            await self.db.refresh(row)
            session.status = constants.UploadStatus.COMPLETED
            session.file_id = row.id
            await self.db.flush()
        except Exception:
            await self._drop_object(session.key)
            raise
        return StoredFileOut.model_validate(queries.to_out_dict(row)), True

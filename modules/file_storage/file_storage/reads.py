"""The read half of :class:`~file_storage.service.FileStorageService`.

Mixed into the service rather than living beside upload/download/delete because
it is a different job with different costs: nothing here touches a storage
backend or mutates a row, and the only thing it has to get right is how much
database work one screen pays for. Keeping it separate is what makes that
question answerable by reading one short file.

The SQL itself is in :mod:`file_storage.queries` (filtered reads) and
:mod:`file_storage.aggregates` (unfiltered bucket totals); these methods are
the seam callers already use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from file_storage import aggregates, queries
from file_storage.contracts.schemas import StoredFileOut

if TYPE_CHECKING:
    from file_storage.aggregates import AggregateCache, StorageAggregates


class FileStorageReads:
    """Listing, paging, counting, and the bucket-wide totals."""

    db: AsyncSession
    _aggregate_cache: AggregateCache | None

    async def list_files(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        created_by: str | None = None,
        search: str | None = None,
        content_type: str | None = None,
    ) -> tuple[list[StoredFileOut], int]:
        return await queries.list_files(
            self.db,
            page=page,
            per_page=per_page,
            created_by=created_by,
            search=search,
            content_type=content_type,
        )

    async def count_files(
        self,
        *,
        created_by: str | None = None,
        search: str | None = None,
        content_type: str | None = None,
    ) -> int:
        return await queries.count_files(
            self.db, created_by=created_by, search=search, content_type=content_type
        )

    async def page_of_files(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        created_by: str | None = None,
        search: str | None = None,
        content_type: str | None = None,
    ) -> list[StoredFileOut]:
        return await queries.page_of_files(
            self.db,
            page=page,
            per_page=per_page,
            created_by=created_by,
            search=search,
            content_type=content_type,
        )

    async def storage_aggregates(self) -> StorageAggregates:
        """Byte usage and both facet lists, from one scan of the bucket.

        The three used to be three unfiltered full-table scans per render. One
        call here so a caller cannot accidentally pay for the scan more than
        once, whether or not a cache is wired in.
        """
        if self._aggregate_cache is None:
            return await aggregates.compute(self.db)
        return await self._aggregate_cache.get(self.db)

    async def content_type_facets(self, *, created_by: str | None = None) -> list[dict]:
        """Types present in the bucket, or in one uploader's slice of it."""
        if created_by is not None:
            return await queries.content_type_facets(self.db, created_by=created_by)
        return [facet.as_dict() for facet in (await self.storage_aggregates()).content_types]

    async def uploader_facets(self) -> list[dict]:
        return [facet.as_dict() for facet in (await self.storage_aggregates()).uploaders]

    async def used_bytes(self) -> int:
        return (await self.storage_aggregates()).used_bytes

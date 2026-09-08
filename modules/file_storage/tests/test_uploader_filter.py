"""Filtering the file table by who uploaded a file.

``service.list_files`` already accepted ``created_by``; nothing exposed it, so
the only way to answer "what did this person upload?" was to read the whole
table. The count has to travel with the filter — a total that ignores it offers
pages that render empty.
"""

from __future__ import annotations

import uuid

import httpx
from file_storage import constants
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.models import StoredFile
from file_storage.service import FileStorageService
from file_storage.settings import FileStorageSettings
from sqlalchemy.ext.asyncio import AsyncSession

VIEW_BASE = f"{constants.ROUTE_PREFIX_VIEW}/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}

ALICE = "11111111-1111-1111-1111-111111111111"
BOB = "22222222-2222-2222-2222-222222222222"


def _service(tmp_path, db_session: AsyncSession) -> FileStorageService:
    settings = FileStorageSettings(
        backend=constants.BackendId.FILESYSTEM,
        fs_root_path=str(tmp_path),
    )
    return FileStorageService(db_session, FilesystemBackend(root=tmp_path), settings)


async def _seed(db_session: AsyncSession, *rows: tuple[str, str | None]) -> None:
    for filename, owner in rows:
        db_session.add(
            StoredFile(
                key=f"2026/01/01/{uuid.uuid4().hex}",
                filename=filename,
                content_type="text/plain",
                size_bytes=1,
                backend=constants.BackendId.FILESYSTEM,
                checksum_sha256="0" * 64,
                created_by=owner,
            )
        )
    await db_session.flush()


class TestServiceFilter:
    async def test_narrows_rows_and_total_together(self, tmp_path, db_session: AsyncSession):
        await _seed(db_session, ("a.txt", ALICE), ("b.txt", ALICE), ("c.txt", BOB))
        svc = _service(tmp_path, db_session)

        items, total = await svc.list_files(created_by=ALICE)

        assert sorted(i.filename for i in items) == ["a.txt", "b.txt"]
        assert total == 2

    async def test_unknown_uploader_matches_nothing(self, tmp_path, db_session: AsyncSession):
        await _seed(db_session, ("a.txt", ALICE))
        svc = _service(tmp_path, db_session)

        items, total = await svc.list_files(created_by=BOB)

        assert items == []
        assert total == 0


class TestUploaderFacets:
    async def test_counts_files_per_uploader(self, tmp_path, db_session: AsyncSession):
        await _seed(db_session, ("a.txt", ALICE), ("b.txt", ALICE), ("c.txt", BOB))
        svc = _service(tmp_path, db_session)

        facets = await svc.uploader_facets()

        assert {f["value"]: f["count"] for f in facets} == {ALICE: 2, BOB: 1}

    async def test_skips_rows_with_no_uploader(self, tmp_path, db_session: AsyncSession):
        """``created_by`` is NULL on pre-audit rows. Offering them as a filter
        value would need a sentinel the query cannot honestly round-trip."""
        await _seed(db_session, ("a.txt", ALICE), ("orphan.txt", None))
        svc = _service(tmp_path, db_session)

        facets = await svc.uploader_facets()

        assert [f["value"] for f in facets] == [ALICE]


class TestBrowseView:
    async def test_filters_the_table_by_uploader(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        async with app.state.sm.db.session_factory() as session:
            await _seed(session, ("mine.txt", ALICE), ("theirs.txt", BOB))
            await session.commit()

        resp = await authenticated_client.get(
            VIEW_BASE, params={"uploaded_by": ALICE}, headers=INERTIA_HEADERS
        )

        assert resp.status_code == 200, resp.text
        props = resp.json()["props"]
        assert [f["filename"] for f in props["files"]] == ["mine.txt"]
        assert props["pagination"]["total"] == 1

    async def test_uploader_facet_is_not_narrowed_by_the_active_filter(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        """A filter that hides its own alternatives is a dead end."""
        async with app.state.sm.db.session_factory() as session:
            await _seed(session, ("mine.txt", ALICE), ("theirs.txt", BOB))
            await session.commit()

        resp = await authenticated_client.get(
            VIEW_BASE, params={"uploaded_by": ALICE}, headers=INERTIA_HEADERS
        )

        ids = {u["id"] for u in resp.json()["props"]["uploaders"]}
        assert ids == {ALICE, BOB}

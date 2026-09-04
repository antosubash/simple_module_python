"""Props the file-storage browse screen renders its header and filters from.

The screen's subtitle states which backend holds the bytes, how much of the
bucket is in use and what a single upload may weigh — none of which the page
could know before this. The quota segment is deliberately conditional: no quota
concept existed, so an install that has not set one must not be told it has 5 GB.
"""

from __future__ import annotations

import httpx
from file_storage import constants

VIEW_BASE = f"{constants.ROUTE_PREFIX_VIEW}/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}
UNKNOWN_UPLOADER = constants.UNKNOWN_UPLOADER


async def _seed_orphan_row(app) -> None:
    """Insert a file with no uploader, the way pre-audit rows look."""
    from file_storage.models import StoredFile

    async with app.state.sm.db.session_factory() as session:
        session.add(
            StoredFile(
                key="2026/01/01/orphan.txt",
                filename="orphan.txt",
                content_type="text/plain",
                size_bytes=3,
                backend=constants.BackendId.FILESYSTEM,
                checksum_sha256="0" * 64,
            )
        )
        await session.commit()


async def _upload(client: httpx.AsyncClient, name: str, body: bytes = b"hi") -> str:
    resp = await client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files={"file": (name, body, "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _browse(client: httpx.AsyncClient, **params: str) -> dict:
    resp = await client.get(VIEW_BASE, params=params, headers=INERTIA_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


class TestStorageFacts:
    async def test_reports_the_active_backend(self, authenticated_client: httpx.AsyncClient):
        props = await _browse(authenticated_client)

        assert props["backend"] == constants.BackendId.FILESYSTEM

    async def test_each_row_names_the_backend_holding_its_bytes(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Not the configured backend: rows ingested before a backend switch
        still live where they landed, and the delete confirm says which."""
        await _upload(authenticated_client, "a.txt")

        props = await _browse(authenticated_client)

        assert [f["backend"] for f in props["files"]] == [constants.BackendId.FILESYSTEM]

    async def test_reports_the_per_file_limit_and_type_allowlist(
        self, authenticated_client: httpx.AsyncClient
    ):
        props = await _browse(authenticated_client)

        assert props["max_file_size_bytes"] == constants.DEFAULT_MAX_FILE_SIZE_BYTES
        # None, not [] — "any type" and "nothing is allowed" must stay distinct.
        assert props["allowed_content_types"] is None

    async def test_used_bytes_sums_the_stored_files(self, authenticated_client: httpx.AsyncClient):
        await _upload(authenticated_client, "a.txt", b"12345")
        await _upload(authenticated_client, "b.txt", b"678")

        props = await _browse(authenticated_client)

        assert props["used_bytes"] == 8

    async def test_used_bytes_ignores_deleted_files(self, authenticated_client: httpx.AsyncClient):
        """A deleted file still has a row (soft delete); its bytes must not
        keep counting against the bucket the reader is looking at."""
        keep = await _upload(authenticated_client, "keep.txt", b"12345")
        gone = await _upload(authenticated_client, "gone.txt", b"678")
        resp = await authenticated_client.delete(
            f"{constants.ROUTE_PREFIX_API}{constants.PATH_FILES}/{gone}"
        )
        assert resp.status_code == 204

        props = await _browse(authenticated_client)

        assert props["used_bytes"] == 5
        assert [f["id"] for f in props["files"]] == [keep]
        # The count has to drop with the rows. A total that keeps counting
        # deleted files offers pages that render empty — and after a bulk
        # delete it is the whole selection, not one row.
        assert props["pagination"]["total"] == 1

    async def test_quota_is_absent_until_configured(self, authenticated_client: httpx.AsyncClient):
        props = await _browse(authenticated_client)

        assert props["quota_bytes"] is None

    async def test_quota_is_reported_when_configured(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        app.state.file_storage.settings.quota_bytes = 5 * 1024**3

        props = await _browse(authenticated_client)

        assert props["quota_bytes"] == 5 * 1024**3


class TestUploaderLabels:
    async def test_rows_carry_a_resolved_uploader_label(
        self, authenticated_client: httpx.AsyncClient
    ):
        """The row stores an opaque user id; a table of uuids names nobody."""
        await _upload(authenticated_client, "a.txt")

        props = await _browse(authenticated_client)

        assert [f["uploaded_by_label"] for f in props["files"]] == ["Test Admin"]

    async def test_unknown_uploader_falls_back_to_a_dash(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        """Rows predating authenticated uploads carry no ``created_by``."""
        await _seed_orphan_row(app)

        props = await _browse(authenticated_client)

        assert [f["uploaded_by_label"] for f in props["files"]] == [UNKNOWN_UPLOADER]


class TestUploaderFacet:
    async def test_offers_every_uploader_with_a_count(
        self, authenticated_client: httpx.AsyncClient
    ):
        await _upload(authenticated_client, "a.txt")
        await _upload(authenticated_client, "b.txt")

        props = await _browse(authenticated_client)

        assert len(props["uploaders"]) == 1
        (uploader,) = props["uploaders"]
        assert uploader["label"] == "Test Admin"
        assert uploader["count"] == 2
        assert uploader["id"]

    async def test_echoes_the_active_uploader_filter(self, authenticated_client: httpx.AsyncClient):
        await _upload(authenticated_client, "a.txt")
        props = await _browse(authenticated_client)
        uploader_id = props["uploaders"][0]["id"]

        filtered = await _browse(authenticated_client, uploaded_by=uploader_id)

        assert filtered["filters"]["uploaded_by"] == uploader_id

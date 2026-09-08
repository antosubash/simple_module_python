"""How much database work one render of ``/file-storage/`` is allowed to cost.

The screen used to issue six queries, five of them against
``file_storage_stored_file`` and three of those deliberately unfiltered full
scans, on every render — including the ones that only changed ``?page=`` (GH
#299). These are shape assertions, not timings: what went wrong was the number
of scans, and a wall-clock budget would be flaky in CI while still passing on
the day a sixth scan is added.
"""

from __future__ import annotations

import httpx
import pytest
from file_storage import constants

VIEW_BASE = f"{constants.ROUTE_PREFIX_VIEW}/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}
TABLE = constants.TABLE_STORED_FILE

# One filtered count, one page of rows, one grouped scan for the bucket totals.
COLD_RENDER_QUERIES = 3
# On a warm cache the totals are already in hand: count and page only.
WARM_RENDER_QUERIES = 2


async def _upload(client: httpx.AsyncClient, name: str, body: bytes = b"hi") -> str:
    resp = await client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files={"file": (name, body, "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _browse(client: httpx.AsyncClient, **params) -> dict:
    resp = await client.get(VIEW_BASE, params=params, headers=INERTIA_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


def _file_queries(seen: list[str]) -> list[str]:
    return [s for s in seen if TABLE in s]


class TestOneRender:
    async def test_a_cold_render_scans_the_table_once(
        self, app, authenticated_client: httpx.AsyncClient, record_statements
    ):
        """Three unfiltered scans — content types, uploaders, byte total —
        collapse into the single grouped one."""
        await _upload(authenticated_client, "a.txt")

        with record_statements(app) as seen:
            await _browse(authenticated_client)

        queries = _file_queries(seen)
        assert len(queries) == COLD_RENDER_QUERIES, queries
        assert sum("GROUP BY" in q.upper() for q in queries) == 1, queries

    async def test_the_second_render_reuses_the_totals(
        self, app, authenticated_client: httpx.AsyncClient, record_statements
    ):
        """Paging through a bucket must not re-price the whole bucket."""
        await _upload(authenticated_client, "a.txt")
        await _browse(authenticated_client)

        with record_statements(app) as seen:
            await _browse(authenticated_client, page=1)

        queries = _file_queries(seen)
        assert len(queries) == WARM_RENDER_QUERIES, queries
        assert not any("GROUP BY" in q.upper() for q in queries), queries


class TestPastTheEndPage:
    @pytest.mark.parametrize("page", [2, 99])
    async def test_clamping_does_not_fetch_the_page_twice(
        self, page: int, app, authenticated_client: httpx.AsyncClient, record_statements
    ):
        """The clamp used to re-run the whole listing, paying for a page of
        rows nobody would ever see. Counting first makes it one page fetch."""
        await _upload(authenticated_client, "a.txt")

        with record_statements(app) as seen:
            props = await _browse(authenticated_client, page=page)

        assert props["pagination"]["page"] == 1
        assert [f["filename"] for f in props["files"]] == ["a.txt"]
        queries = _file_queries(seen)
        assert len(queries) == COLD_RENDER_QUERIES, queries
        assert sum("LIMIT" in q.upper() for q in queries) == 1, queries


class TestCachedTotalsStayHonest:
    async def test_an_upload_is_reflected_on_the_next_render(
        self, authenticated_client: httpx.AsyncClient
    ):
        """The cache may be seconds stale about someone else's write; it must
        never be stale about the one this request just made."""
        await _upload(authenticated_client, "a.txt", b"12345")
        assert (await _browse(authenticated_client))["used_bytes"] == 5

        await _upload(authenticated_client, "b.txt", b"678")

        props = await _browse(authenticated_client)
        assert props["used_bytes"] == 8
        assert {u["count"] for u in props["uploaders"]} == {2}

    async def test_a_delete_is_reflected_on_the_next_render(
        self, authenticated_client: httpx.AsyncClient
    ):
        await _upload(authenticated_client, "keep.txt", b"12345")
        gone = await _upload(authenticated_client, "gone.txt", b"678")
        assert (await _browse(authenticated_client))["used_bytes"] == 8

        resp = await authenticated_client.delete(
            f"{constants.ROUTE_PREFIX_API}{constants.PATH_FILES}/{gone}"
        )
        assert resp.status_code == 204

        assert (await _browse(authenticated_client))["used_bytes"] == 5

    async def test_a_bulk_delete_is_reflected_on_the_next_render(
        self, authenticated_client: httpx.AsyncClient
    ):
        first = await _upload(authenticated_client, "a.txt", b"12345")
        second = await _upload(authenticated_client, "b.txt", b"678")
        assert (await _browse(authenticated_client))["used_bytes"] == 8

        resp = await authenticated_client.post(
            f"{constants.ROUTE_PREFIX_API}{constants.PATH_FILES_BULK_DELETE}",
            json={"ids": [first, second]},
        )
        assert resp.status_code == 200, resp.text

        props = await _browse(authenticated_client)
        assert props["used_bytes"] == 0
        assert props["content_types"] == []
        assert props["uploaders"] == []

    async def test_a_write_outside_the_request_path_still_drops_the_cache(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        """Invalidation hangs off the commit, not off ``FileUploaded`` — so a
        seed script or a fix-up in the shell is seen too."""
        from file_storage.models import StoredFile

        assert (await _browse(authenticated_client))["used_bytes"] == 0

        async with app.state.sm.db.session_factory() as session:
            session.add(
                StoredFile(
                    key="2026/01/01/seeded.txt",
                    filename="seeded.txt",
                    content_type="text/plain",
                    size_bytes=42,
                    backend=constants.BackendId.FILESYSTEM,
                    checksum_sha256="0" * 64,
                )
            )
            await session.commit()

        assert (await _browse(authenticated_client))["used_bytes"] == 42

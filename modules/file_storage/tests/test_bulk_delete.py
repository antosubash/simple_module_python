"""Deleting a selection of files in one request.

The table gained checkboxes and a "Delete selected" button; only single-file
delete existed, so a selection of twenty meant twenty round trips and twenty
chances to fail halfway. The endpoint reports how many rows it actually
removed, because ids the caller sent may already be gone.
"""

from __future__ import annotations

import uuid

import httpx
from file_storage import constants
from file_storage.contracts.events import FileDeleted

BULK_DELETE = f"{constants.ROUTE_PREFIX_API}{constants.PATH_FILES_BULK_DELETE}"
LIST_FILES = f"{constants.ROUTE_PREFIX_API}{constants.PATH_FILES}"


async def _upload(client: httpx.AsyncClient, name: str) -> str:
    resp = await client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files={"file": (name, b"payload", "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _filenames(client: httpx.AsyncClient) -> list[str]:
    resp = await client.get(LIST_FILES)
    assert resp.status_code == 200, resp.text
    return sorted(item["filename"] for item in resp.json()["items"])


class TestBulkDelete:
    async def test_removes_every_selected_file(self, authenticated_client: httpx.AsyncClient):
        first = await _upload(authenticated_client, "a.txt")
        second = await _upload(authenticated_client, "b.txt")
        await _upload(authenticated_client, "keep.txt")

        resp = await authenticated_client.post(BULK_DELETE, json={"ids": [first, second]})

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"deleted": 2}
        assert await _filenames(authenticated_client) == ["keep.txt"]

    async def test_ids_that_are_already_gone_do_not_fail_the_batch(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Two admins clearing the same selection must not leave the second
        one staring at a 404 with half the rows deleted."""
        real = await _upload(authenticated_client, "a.txt")

        resp = await authenticated_client.post(BULK_DELETE, json={"ids": [real, str(uuid.uuid4())]})

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"deleted": 1}
        assert await _filenames(authenticated_client) == []

    async def test_an_empty_selection_deletes_nothing(
        self, authenticated_client: httpx.AsyncClient
    ):
        await _upload(authenticated_client, "a.txt")

        resp = await authenticated_client.post(BULK_DELETE, json={"ids": []})

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"deleted": 0}
        assert await _filenames(authenticated_client) == ["a.txt"]

    async def test_announces_each_removal_on_the_event_bus(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        """Subscribers that mirror or index files must hear about a bulk
        delete exactly as they hear about a single one."""
        seen: list[str] = []

        async def _record(event: FileDeleted) -> None:
            seen.append(str(event.file_id))

        app.state.sm.event_bus.subscribe(FileDeleted, _record)
        first = await _upload(authenticated_client, "a.txt")
        second = await _upload(authenticated_client, "b.txt")

        await authenticated_client.post(BULK_DELETE, json={"ids": [first, second]})

        assert sorted(seen) == sorted([first, second])


class TestBounds:
    async def test_rejects_a_selection_larger_than_a_page(
        self, authenticated_client: httpx.AsyncClient
    ):
        """The ids become one ``IN (...)``; an unbounded list lets a single
        request build a statement the driver refuses instead of us."""
        resp = await authenticated_client.post(
            BULK_DELETE, json={"ids": [str(uuid.uuid4()) for _ in range(201)]}
        )

        assert resp.status_code == 422


class TestPermissions:
    async def test_unauthenticated_request_is_rejected(self, client: httpx.AsyncClient):
        resp = await client.post(BULK_DELETE, json={"ids": []}, follow_redirects=False)

        assert resp.status_code in {302, 401, 403}

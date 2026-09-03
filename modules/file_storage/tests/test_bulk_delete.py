"""Deleting a selection of files in one request.

The table gained checkboxes and a "Delete selected" button; only single-file
delete existed, so a selection of twenty meant twenty round trips and twenty
chances to fail halfway. The endpoint reports how many rows it actually
removed, because ids the caller sent may already be gone.
"""

from __future__ import annotations

import uuid
from io import BytesIO

import httpx
from fastapi import UploadFile
from file_storage import constants
from file_storage.contracts.events import FileDeleted
from simple_module_test import forge_session_cookie

BULK_DELETE = f"{constants.ROUTE_PREFIX_API}{constants.PATH_FILES_BULK_DELETE}"
LIST_FILES = f"{constants.ROUTE_PREFIX_API}{constants.PATH_FILES}"


async def _upload(client: httpx.AsyncClient, name: str) -> str:
    resp = await client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files={"file": (name, b"payload", "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _upload_file(name: str) -> UploadFile:
    return UploadFile(
        filename=name,
        file=BytesIO(b"payload"),
        headers={"content-type": "text/plain"},  # type: ignore[arg-type]
    )


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
        body = resp.json()
        assert body["deleted"] == 2
        assert sorted(body["ids"]) == sorted([first, second])
        assert await _filenames(authenticated_client) == ["keep.txt"]

    async def test_ids_that_are_already_gone_do_not_fail_the_batch(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Two admins clearing the same selection must not leave the second
        one staring at a 404 with half the rows deleted."""
        real = await _upload(authenticated_client, "a.txt")

        resp = await authenticated_client.post(BULK_DELETE, json={"ids": [real, str(uuid.uuid4())]})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] == 1
        # The screen names a file only when exactly one id comes back, so that
        # id has to be the one actually *removed* — naming the first thing the
        # user selected would credit a deletion that never happened.
        assert body["ids"] == [real]
        assert await _filenames(authenticated_client) == []

    async def test_an_empty_selection_deletes_nothing(
        self, authenticated_client: httpx.AsyncClient
    ):
        await _upload(authenticated_client, "a.txt")

        resp = await authenticated_client.post(BULK_DELETE, json={"ids": []})

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"deleted": 0, "ids": []}
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


class TestBackendFailures:
    async def test_one_unreachable_object_does_not_abort_the_batch(self, tmp_path, db_session):
        """The rows are already marked deleted by the time objects are dropped.
        Letting one unreachable object raise would 500 the request, tell the
        caller nothing happened, and leave the rest behind as orphans."""
        from file_storage.backends.filesystem import FilesystemBackend
        from file_storage.service import FileStorageService
        from file_storage.settings import FileStorageSettings

        class OneBadKey(FilesystemBackend):
            async def delete(self, key: str) -> None:
                if key.endswith("boom.txt"):
                    raise OSError("backend is on fire")
                await super().delete(key)

        settings = FileStorageSettings(
            backend=constants.BackendId.FILESYSTEM, fs_root_path=str(tmp_path)
        )
        svc = FileStorageService(db_session, OneBadKey(root=tmp_path), settings)
        good = await svc.upload(_upload_file("fine.txt"))
        bad = await svc.upload(_upload_file("boom.txt"))

        removed = await svc.delete_many([good.id, bad.id])

        assert sorted(r.filename for r in removed) == ["boom.txt", "fine.txt"]
        # Both rows are gone from the listing — the failure is a janitor's
        # problem, not something the caller has to retry.
        items, total = await svc.list_files()
        assert items == []
        assert total == 0


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

    async def test_download_only_caller_cannot_delete(self, app):
        """Reading the bucket and emptying it are separate grants.

        The module maps its own ``user`` role to upload+download+delete, so a
        plain account proves nothing here — this caller holds exactly
        ``file_storage.download`` and must be refused.
        """
        async with await _reader_client(app) as reader:
            listed = await reader.get(LIST_FILES)
            forbidden = await reader.post(BULK_DELETE, json={"ids": []})

        # Listing proves the session is real, so the 403 is about the missing
        # permission rather than a caller who never authenticated at all.
        assert listed.status_code == 200, listed.text
        assert forbidden.status_code == 403


READER_ROLE = "file_storage_reader"


async def _reader_client(app) -> httpx.AsyncClient:
    """A signed-in caller holding ``file_storage.download`` and nothing else.

    Built rather than reused: the module maps its own ``user`` role to
    upload+download+delete, so no seeded account can stand in for "may read the
    bucket, may not empty it".
    """
    from users.models import Role, User, UserRole

    # Role → permission mapping lives in the registry, not the DB.
    app.state.sm.permissions.map_role(READER_ROLE, [constants.Permission.DOWNLOAD])

    async with app.state.sm.db.session_factory() as session:
        role = Role(name=READER_ROLE, description="Download only")
        user = User(
            email="reader@test",
            hashed_password="not-a-real-hash",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add_all([role, user])
        await session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.commit()
        user_id = str(user.id)

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies={
            "session": forge_session_cookie(
                str(app.state.sm.settings.secret_key), {"user_id": user_id}
            )
        },
    )

"""Quota and size limits hold for what is really stored, not what was declared (#454)."""

from __future__ import annotations

import pytest
from file_storage import constants
from file_storage_uploads_helpers import API, PART, open_session, payload, upload_all

pytestmark = pytest.mark.usefixtures("checksum_calls")


class TestQuotaIsEnforcedOnWhatIsReallyStored:
    async def test_open_sessions_count_against_the_quota(self, authenticated_client, storage):
        storage.settings.quota_bytes = PART * 2
        assert (await open_session(authenticated_client, total=PART)).status_code == 201
        assert (await open_session(authenticated_client, total=PART)).status_code == 201
        third = await open_session(authenticated_client, total=1)
        assert third.status_code == 413
        assert third.json()["detail"]["code"] == constants.ErrorCode.QUOTA_EXCEEDED

    async def test_stored_files_and_open_sessions_add_up(self, authenticated_client, storage):
        storage.settings.quota_bytes = PART + 10
        await authenticated_client.post(
            f"{API}/upload", files={"file": ("a.bin", b"x" * 20, "application/octet-stream")}
        )
        assert (await open_session(authenticated_client, total=PART)).status_code == 413

    async def test_aborted_sessions_release_their_reservation(self, authenticated_client, storage):
        storage.settings.quota_bytes = PART
        sid = (await open_session(authenticated_client, total=PART)).json()["id"]
        assert (await open_session(authenticated_client, total=PART)).status_code == 413
        await authenticated_client.delete(f"{API}/uploads/{sid}")
        assert (await open_session(authenticated_client, total=PART)).status_code == 201

    async def test_complete_rechecks_quota_against_the_stored_size(
        self, authenticated_client, storage
    ):
        data = payload(PART)
        sid = (await open_session(authenticated_client, total=len(data))).json()["id"]
        await upload_all(authenticated_client, sid, data)
        # Tightened after the session opened (an admin change, or other uploads).
        storage.settings.quota_bytes = PART - 1
        resp = await authenticated_client.post(f"{API}/uploads/{sid}/complete", json={})
        assert resp.status_code == 413
        assert resp.json()["detail"]["code"] == constants.ErrorCode.QUOTA_EXCEEDED
        listing = (await authenticated_client.get(f"{API}/files")).json()
        assert listing["total"] == 0
        assert not list(storage.backend.root.glob("*/*/**/*.bin"))

    async def test_complete_rechecks_the_direct_upload_maximum(self, authenticated_client, storage):
        data = payload(PART)
        sid = (await open_session(authenticated_client, total=len(data))).json()["id"]
        await upload_all(authenticated_client, sid, data)
        storage.settings.max_direct_upload_bytes = PART - 1
        resp = await authenticated_client.post(f"{API}/uploads/{sid}/complete", json={})
        assert resp.status_code == 413
        assert resp.json()["detail"]["code"] == constants.ErrorCode.TOO_LARGE

    async def test_assembled_size_must_equal_the_declared_total(
        self, authenticated_client, storage, monkeypatch
    ):
        """An object bigger than declared (a store that let an oversized part through)."""
        data = payload(PART)
        sid = (await open_session(authenticated_client, total=len(data))).json()["id"]
        await upload_all(authenticated_client, sid, data)
        real_head = storage.backend.head

        async def lying_head(key):
            info = await real_head(key)
            return type(info)(size=info.size + 1, etag=info.etag)

        monkeypatch.setattr(storage.backend, "head", lying_head)
        resp = await authenticated_client.post(f"{API}/uploads/{sid}/complete", json={})
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == constants.ErrorCode.SIZE_MISMATCH
        assert (await authenticated_client.get(f"{API}/files")).json()["total"] == 0
        assert not await real_head_exists(storage.backend, sid)


async def real_head_exists(backend, _sid) -> bool:
    return any(p.is_file() for p in backend.root.glob("*/*/*/*/*/*.bin"))

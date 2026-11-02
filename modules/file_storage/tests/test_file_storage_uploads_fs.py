"""Resumable multipart uploads end-to-end on the filesystem backend (#454)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from file_storage import constants
from file_storage.contracts.events import FileUploaded
from file_storage.models import StoredFile, UploadSession
from file_storage_uploads_helpers import API, MIB, PART, open_session, payload, put_part, upload_all
from simple_module_db import all_tenants, tenant_context
from sqlalchemy import select, update

pytestmark = pytest.mark.usefixtures("checksum_calls")


async def _expire_everything(app) -> None:
    async with app.state.sm.db.session_factory() as db:
        with all_tenants():
            await db.execute(
                update(UploadSession).values(expires_at=datetime.now(UTC) - timedelta(hours=1))
            )
        await db.commit()


async def test_full_flow_creates_a_stored_file_and_publishes_the_event(
    app, authenticated_client, storage, checksum_calls
):
    seen = []

    async def _collect(event):
        seen.append(event)

    app.state.sm.event_bus.subscribe(FileUploaded, _collect)
    data = payload(PART * 2 + 123)

    created = await open_session(authenticated_client, total=len(data))
    assert created.status_code == 201, created.text
    session = created.json()
    assert session["part_size"] == PART
    assert session["total_parts"] == 3
    assert session["parts"] == []

    # Parts can arrive out of order, and a reload lists what the backend holds.
    etags = await upload_all(authenticated_client, session["id"], data, only={3, 1})
    resumed = await authenticated_client.get(f"{API}/uploads/{session['id']}")
    assert [p["no"] for p in resumed.json()["parts"]] == [1, 3]

    etags.update(await upload_all(authenticated_client, session["id"], data, only={2}))
    done = await authenticated_client.post(
        f"{API}/uploads/{session['id']}/complete",
        json={"parts": [{"n": n, "etag": e} for n, e in etags.items()]},
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "completed"
    file = body["file"]
    assert file["size_bytes"] == len(data)
    assert file["checksum_sha256"] is None

    download = await authenticated_client.get(f"{API}/files/{file['id']}/download")
    assert download.status_code == 200
    assert download.content == data
    assert [e.file_id for e in seen] == [uuid.UUID(file["id"])]
    assert checksum_calls == [
        (constants.Task.COMPUTE_CHECKSUM, (file["id"], file["key"].split("/")[0]))
    ]

    # A retried complete answers with the same file and publishes nothing new.
    again = await authenticated_client.post(f"{API}/uploads/{session['id']}/complete", json={})
    assert again.status_code == 200
    assert again.json()["file"]["id"] == file["id"]
    assert len(seen) == 1
    assert len(checksum_calls) == 1


async def test_part_urls_point_at_the_app_for_filesystem(authenticated_client, storage):
    session = (await open_session(authenticated_client, total=PART + 1)).json()
    resp = await authenticated_client.post(
        f"{API}/uploads/{session['id']}/part-urls", json={"parts": [1, 2]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["direct"] is False
    assert body["urls"]["1"] == f"{API}/uploads/{session['id']}/parts/1"

    bad = await authenticated_client.post(
        f"{API}/uploads/{session['id']}/part-urls", json={"parts": [3]}
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == constants.ErrorCode.BAD_PART


async def test_complete_with_missing_parts_is_rejected_and_resumable(authenticated_client, storage):
    data = payload(PART * 2)
    session = (await open_session(authenticated_client, total=len(data))).json()
    await upload_all(authenticated_client, session["id"], data, only={1})

    resp = await authenticated_client.post(f"{API}/uploads/{session['id']}/complete", json={})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == constants.ErrorCode.PARTS_MISMATCH
    assert detail["missing"] == [2]

    await upload_all(authenticated_client, session["id"], data, only={2})
    done = await authenticated_client.post(f"{API}/uploads/{session['id']}/complete", json={})
    assert done.status_code == 200


async def test_wrong_etag_is_a_mismatch(authenticated_client, storage):
    data = payload(PART)
    session = (await open_session(authenticated_client, total=len(data))).json()
    await upload_all(authenticated_client, session["id"], data)
    resp = await authenticated_client.post(
        f"{API}/uploads/{session['id']}/complete", json={"parts": [{"n": 1, "etag": "nope"}]}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["mismatched"] == [1]


async def test_a_part_of_the_wrong_size_is_refused(authenticated_client, storage):
    session = (await open_session(authenticated_client, total=PART * 2)).json()
    short = await put_part(authenticated_client, session["id"], 1, b"x" * 10)
    assert short.status_code == 400
    assert short.json()["detail"]["code"] == constants.ErrorCode.BAD_PART
    long = await put_part(authenticated_client, session["id"], 1, b"x" * (PART + 1))
    assert long.status_code == 400
    assert (await put_part(authenticated_client, session["id"], 9, b"x")).status_code == 400


async def test_abort_discards_the_parts_and_closes_the_session(authenticated_client, storage):
    data = payload(PART)
    session = (await open_session(authenticated_client, total=len(data))).json()
    await upload_all(authenticated_client, session["id"], data)
    assert (await authenticated_client.delete(f"{API}/uploads/{session['id']}")).status_code == 204

    assert not list((storage.backend.root / constants.FS_MULTIPART_DIR).glob("*"))
    got = await authenticated_client.get(f"{API}/uploads/{session['id']}")
    assert got.json()["status"] == "aborted"
    closed = await put_part(authenticated_client, session["id"], 1, data)
    assert closed.status_code == 409
    assert closed.json()["detail"]["code"] == constants.ErrorCode.SESSION_CLOSED


async def test_creating_a_session_reaps_the_callers_expired_ones(
    app, authenticated_client, storage
):
    old = (await open_session(authenticated_client, total=PART)).json()
    await _expire_everything(app)

    assert (await open_session(authenticated_client, total=PART)).status_code == 201
    got = await authenticated_client.get(f"{API}/uploads/{old['id']}")
    assert got.json()["status"] == "aborted"
    assert not (storage.backend.root / constants.FS_MULTIPART_DIR / old["id"]).exists()


async def test_an_expired_session_cannot_take_parts(app, authenticated_client, storage):
    session = (await open_session(authenticated_client, total=PART)).json()
    await _expire_everything(app)
    resp = await put_part(authenticated_client, session["id"], 1, b"x" * PART)
    assert resp.status_code == 409
    # The abort that discovering the expiry performed outlives the 409.
    got = await authenticated_client.get(f"{API}/uploads/{session['id']}")
    assert got.json()["status"] == "aborted"
    urls = await authenticated_client.post(
        f"{API}/uploads/{session['id']}/part-urls", json={"parts": [1]}
    )
    assert urls.status_code == 409


class TestValidation:
    async def test_disallowed_type(self, authenticated_client, storage):
        storage.settings.allowed_content_types = ["text/plain"]
        resp = await open_session(authenticated_client, total=PART, content_type="image/png")
        assert resp.status_code == 415
        assert resp.json()["detail"]["code"] == constants.ErrorCode.BAD_TYPE

    async def test_over_the_direct_upload_maximum(self, authenticated_client, storage):
        storage.settings.max_direct_upload_bytes = 10 * MIB
        resp = await open_session(authenticated_client, total=11 * MIB)
        assert resp.status_code == 413
        assert resp.json()["detail"]["max_bytes"] == 10 * MIB

    async def test_over_quota(self, authenticated_client, storage):
        storage.settings.quota_bytes = PART - 1
        resp = await open_session(authenticated_client, total=PART)
        assert resp.status_code == 413
        assert resp.json()["detail"]["code"] == constants.ErrorCode.QUOTA_EXCEEDED

    async def test_unsupported_backend(self, authenticated_client, storage):
        class Plain:
            backend_id = "plain"
            supports_presigned_url = False

        storage.backend = Plain()
        resp = await open_session(authenticated_client, total=PART)
        assert resp.status_code == 501
        assert resp.json()["detail"]["code"] == constants.ErrorCode.DIRECT_UNSUPPORTED

    async def test_needs_a_session(self, client):
        assert (await open_session(client, total=PART)).status_code in {401, 403}

    async def test_part_size_grows_to_stay_under_ten_thousand_parts(
        self, authenticated_client, storage
    ):
        storage.settings.max_direct_upload_bytes = 1000 * 1024 * MIB
        total = 500 * 1024 * MIB
        body = (await open_session(authenticated_client, total=total)).json()
        assert body["total_parts"] <= constants.MAX_UPLOAD_PARTS
        assert body["part_size"] % MIB == 0
        assert body["part_size"] > PART


class TestOwnership:
    async def test_other_tenants_cannot_touch_a_session(self, tenant_client, storage):
        async with tenant_client() as owner, tenant_client() as stranger:
            sid = (await open_session(owner.client, total=PART)).json()["id"]
            assert (await owner.client.get(f"{API}/uploads/{sid}")).status_code == 200

            for call in (
                stranger.client.get(f"{API}/uploads/{sid}"),
                stranger.client.delete(f"{API}/uploads/{sid}"),
                stranger.client.post(f"{API}/uploads/{sid}/complete", json={}),
                stranger.client.post(f"{API}/uploads/{sid}/part-urls", json={"parts": [1]}),
                put_part(stranger.client, sid, 1, b"x"),
            ):
                assert (await call).status_code == 404

            assert (await owner.client.get(f"{API}/uploads/{sid}")).json()["status"] == "active"

    async def test_a_colleague_in_the_same_tenant_cannot_either(self, tenant_client, storage):
        async with tenant_client() as owner, tenant_client(tenant_id=owner.tenant_id) as colleague:
            sid = (await open_session(owner.client, total=PART)).json()["id"]
            assert (await colleague.client.get(f"{API}/uploads/{sid}")).status_code == 404
            assert (await colleague.client.delete(f"{API}/uploads/{sid}")).status_code == 404
            assert (await put_part(colleague.client, sid, 1, b"x")).status_code == 404

    async def test_the_file_belongs_to_the_owners_tenant(self, app, tenant_client, storage):
        data = payload(PART)
        async with tenant_client() as owner:
            sid = (await open_session(owner.client, total=len(data))).json()["id"]
            await upload_all(owner.client, sid, data)
            out = (await owner.client.post(f"{API}/uploads/{sid}/complete", json={})).json()
            assert out["file"]["key"].startswith(f"{owner.tenant_id}/")
        async with app.state.sm.db.session_factory() as db:
            with tenant_context(owner.tenant_id):
                rows = (await db.execute(select(StoredFile))).scalars().all()
            assert [r.tenant_id for r in rows] == [owner.tenant_id]


def test_no_checksum_task_without_background_tasks(checksum_calls):
    from types import SimpleNamespace

    from file_storage.checksum import schedule_checksum

    file_id = uuid.uuid4()
    bare = SimpleNamespace(state=SimpleNamespace())
    assert schedule_checksum(bare, object(), file_id, "t") is False
    assert checksum_calls == []

    wired = SimpleNamespace(state=SimpleNamespace(background_tasks=object()))
    assert schedule_checksum(wired, object(), file_id, "t") is True
    assert checksum_calls == [(constants.Task.COMPUTE_CHECKSUM, (str(file_id), "t"))]


def test_the_part_route_gets_a_body_limit_of_one_part(app, storage):
    registry = app.state.body_limits
    path = f"{API}/uploads/{uuid.uuid4()}/parts/3"
    limit = registry.limit_for("PUT", path, app)
    assert limit == PART + constants.PART_BODY_SLACK_BYTES
    # Only PUT, only that shape: nothing else under /uploads gets the headroom.
    assert registry.limit_for("POST", path, app) is None
    assert registry.limit_for("PUT", f"{API}/uploads/x/complete", app) is None

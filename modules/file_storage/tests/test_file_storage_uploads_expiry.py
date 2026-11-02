"""Expiry and retention of upload session rows (#454)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from file_storage import constants
from file_storage.models import UploadSession
from file_storage_uploads_helpers import API, PART, open_session
from simple_module_db import all_tenants
from sqlalchemy import select, update

pytestmark = pytest.mark.usefixtures("checksum_calls")


async def _expire_everything(app) -> None:
    async with app.state.sm.db.session_factory() as db:
        with all_tenants():
            await db.execute(
                update(UploadSession).values(expires_at=datetime.now(UTC) - timedelta(hours=1))
            )
        await db.commit()


async def test_opening_an_expired_session_persists_the_abort(app, authenticated_client, storage):
    session = (await open_session(authenticated_client, total=PART)).json()
    await _expire_everything(app)
    urls = await authenticated_client.post(
        f"{API}/uploads/{session['id']}/part-urls", json={"parts": [1]}
    )
    assert urls.status_code == 409
    assert urls.json()["detail"]["code"] == constants.ErrorCode.SESSION_CLOSED
    async with app.state.sm.db.session_factory() as db:
        with all_tenants():
            row = (await db.execute(select(UploadSession))).scalar_one()
    assert row.status == "aborted"
    assert not (storage.backend.root / constants.FS_MULTIPART_DIR / session["id"]).exists()


async def test_creating_a_session_purges_the_callers_old_finished_rows(
    app, authenticated_client, storage
):
    old = (await open_session(authenticated_client, total=PART)).json()
    await authenticated_client.delete(f"{API}/uploads/{old['id']}")
    recent = (await open_session(authenticated_client, total=PART)).json()
    await authenticated_client.delete(f"{API}/uploads/{recent['id']}")
    stale = datetime.now(UTC) - timedelta(days=storage.settings.upload_session_retention_days + 1)
    async with app.state.sm.db.session_factory() as db:
        with all_tenants():
            await db.execute(
                update(UploadSession)
                .where(UploadSession.id == uuid.UUID(old["id"]))
                .values(expires_at=stale)
            )
        await db.commit()

    live = (await open_session(authenticated_client, total=PART)).json()
    async with app.state.sm.db.session_factory() as db:
        with all_tenants():
            ids = {str(i) for i in (await db.execute(select(UploadSession.id))).scalars()}
    assert ids == {recent["id"], live["id"]}

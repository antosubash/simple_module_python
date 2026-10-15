"""Concurrency guarantees that only a real Postgres can show (#454).

SQLite serialises writers, so the quota reservation race and the row lock on
``complete`` are invisible there. Run with ``SM_TEST_DATABASE_URL`` pointing at
Postgres and ``-p no:anyio`` (``make test-py-pg``); skipped otherwise.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from file_storage import constants
from file_storage_uploads_helpers import API, PART, open_session, payload, upload_all

pytestmark = [
    pytest.mark.usefixtures("checksum_calls"),
    pytest.mark.skipif(
        not os.environ.get("SM_TEST_DATABASE_URL", "").startswith("postgresql"),
        reason="needs SM_TEST_DATABASE_URL on Postgres",
    ),
]


async def test_concurrent_openers_cannot_overbook_the_quota(authenticated_client, storage):
    storage.settings.quota_bytes = PART * 2

    responses = await asyncio.gather(
        *(open_session(authenticated_client, total=PART) for _ in range(6))
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 201, 413, 413, 413, 413], codes
    assert all(
        r.json()["detail"]["code"] == constants.ErrorCode.QUOTA_EXCEEDED
        for r in responses
        if r.status_code == 413
    )


async def test_concurrent_completes_record_one_file(authenticated_client, storage, checksum_calls):
    data = payload(PART + 7)
    sid = (await open_session(authenticated_client, total=len(data))).json()["id"]
    etags = await upload_all(authenticated_client, sid, data)
    body = {"parts": [{"n": n, "etag": e} for n, e in etags.items()]}

    responses = await asyncio.gather(
        *(authenticated_client.post(f"{API}/uploads/{sid}/complete", json=body) for _ in range(4))
    )

    assert [r.status_code for r in responses] == [200] * 4, [r.text for r in responses]
    assert len({r.json()["file"]["id"] for r in responses}) == 1
    assert (await authenticated_client.get(f"{API}/files")).json()["total"] == 1
    assert len(checksum_calls) == 1

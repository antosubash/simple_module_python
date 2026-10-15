"""Opt-in: multipart upload against the shared dev S3 (RustFS/MinIO) (#454).

Skipped unless ``SM_TEST_S3_ENDPOINT`` is set, e.g.::

    SM_TEST_S3_ENDPOINT=http://localhost:9000 uv run pytest \\
        modules/file_storage/tests/test_file_storage_uploads_minio.py

Credentials default to the dev stack's ``minioadmin``/``minioadmin`` and the
test creates (and leaves) a bucket named ``sm-multipart-test``.
"""

from __future__ import annotations

import contextlib
import os
from datetime import timedelta

import boto3
import httpx
import pytest
from file_storage import constants
from file_storage.backends import build_backend
from file_storage.settings import FileStorageSettings
from file_storage_uploads_helpers import MIB

ENDPOINT = os.environ.get("SM_TEST_S3_ENDPOINT")
BUCKET = "sm-multipart-test"
PART = 5 * MIB

pytestmark = pytest.mark.skipif(not ENDPOINT, reason="SM_TEST_S3_ENDPOINT not set")


async def test_two_part_upload_against_real_s3():
    creds = {
        "aws_access_key_id": os.environ.get("SM_TEST_S3_KEY", "minioadmin"),
        "aws_secret_access_key": os.environ.get("SM_TEST_S3_SECRET", "minioadmin"),
    }
    client = boto3.client("s3", region_name="us-east-1", endpoint_url=ENDPOINT, **creds)
    with contextlib.suppress(client.exceptions.ClientError):
        client.create_bucket(Bucket=BUCKET)

    backend = build_backend(
        FileStorageSettings(
            backend=constants.BackendId.S3,
            s3_bucket=BUCKET,
            s3_region="us-east-1",
            s3_endpoint_url=ENDPOINT,
            s3_access_key_id=creds["aws_access_key_id"],
            s3_secret_access_key=creds["aws_secret_access_key"],
        )
    )
    key = "multipart/real.bin"
    upload_id = await backend.create_multipart(key, "application/octet-stream")
    async with httpx.AsyncClient() as http:
        for n, body in ((1, b"a" * PART), (2, b"tail")):
            resp = await http.put(await backend.presign_part(key, upload_id, n, 300), content=body)
            assert resp.status_code == 200, resp.text

    # The janitor's orphan listing honours the age cut-off (moto cannot show it).
    assert (key, upload_id) not in await backend.list_stale_multipart(timedelta(days=1))
    assert (key, upload_id) in await backend.list_stale_multipart(timedelta(seconds=-60))

    parts = await backend.list_parts(key, upload_id)
    await backend.complete_multipart(key, upload_id, parts)
    assert (await backend.head(key)).size == PART + 4
    await backend.delete(key)

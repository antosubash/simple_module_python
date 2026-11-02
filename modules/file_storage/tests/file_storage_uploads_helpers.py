"""Shared helpers for the file_storage upload tests (imported, not collected)."""

from __future__ import annotations

import hashlib

import httpx
from file_storage import constants

API = constants.ROUTE_PREFIX_API
MIB = constants.MIB
PART = 5 * MIB  # the smallest part size the settings accept
INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


async def upload_text(client: httpx.AsyncClient, name: str, body: bytes = b"hi") -> str:
    """Upload ``body`` as a one-shot ``text/plain`` file; return its id."""
    resp = await client.post(f"{API}/upload", files={"file": (name, body, "text/plain")})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def open_session(
    client: httpx.AsyncClient,
    *,
    filename: str = "big.bin",
    total: int,
    content_type: str = "application/octet-stream",
    public: bool = False,
) -> httpx.Response:
    return await client.post(
        f"{API}/uploads",
        json={
            "filename": filename,
            "content_type": content_type,
            "total_size": total,
            "public": public,
        },
    )


async def put_part(client: httpx.AsyncClient, upload_id: str, n: int, body: bytes):
    return await client.put(f"{API}/uploads/{upload_id}/parts/{n}", content=body)


def payload(total: int) -> bytes:
    block = hashlib.sha256(b"seed").digest()
    return (block * (total // len(block) + 1))[:total]


async def upload_all(client, upload_id: str, data: bytes, only=None):
    etags = {}
    for i in range(0, len(data), PART):
        n = i // PART + 1
        if only is not None and n not in only:
            continue
        resp = await put_part(client, upload_id, n, data[i : i + PART])
        assert resp.status_code == 200, resp.text
        etags[n] = resp.json()["etag"]
    return etags

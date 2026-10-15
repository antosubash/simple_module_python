"""Shared helpers for the resumable-upload tests (imported, not collected)."""

from __future__ import annotations

import httpx
from file_storage import constants

API = constants.ROUTE_PREFIX_API
MIB = constants.MIB


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

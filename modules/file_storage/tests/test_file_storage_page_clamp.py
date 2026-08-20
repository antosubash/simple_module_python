"""``?page=0`` / ``?page=-1`` on the browse view must clamp, not 422.

The view's ``page`` param used to be a strict ``Query(..., ge=1)``, so a
hand-edited or bookmarked ``?page=0``/``?page=-1`` was rejected before the
listing ever ran and rendered the app's raw "invalid parameters" error page
instead of page 1 — unlike the already-working past-the-end clamp, which
re-queries and shows rows.
"""

from __future__ import annotations

import httpx
import pytest
from file_storage import constants

VIEW_BASE = f"{constants.ROUTE_PREFIX_VIEW}/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}


async def _upload(client: httpx.AsyncClient, name: str) -> None:
    resp = await client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files={"file": (name, b"hi", "text/plain")},
    )
    assert resp.status_code == 201, resp.text


class TestPageBelowOneClamps:
    @pytest.mark.parametrize("page", [0, -1])
    async def test_clamps_to_page_one_and_renders_rows(
        self,
        page: int,
        authenticated_client: httpx.AsyncClient,
    ) -> None:
        await _upload(authenticated_client, "hello.txt")

        resp = await authenticated_client.get(
            VIEW_BASE, params={"page": page}, headers=INERTIA_HEADERS
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["component"] == constants.PAGE_BROWSE
        assert body["props"]["pagination"]["page"] == 1
        assert [f["filename"] for f in body["props"]["files"]] == ["hello.txt"]

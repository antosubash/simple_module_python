"""GH #468: API timestamps carry a UTC offset even on SQLite.

Without one the browser parses ``2026-10-14T10:40:52`` as local time, so a
file uploaded a moment ago shows "2h ago" at UTC+2.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from file_storage import constants


def _assert_utc(stamp: str) -> None:
    assert stamp.endswith(("+00:00", "Z")), stamp
    assert abs(datetime.now(UTC) - datetime.fromisoformat(stamp)) < timedelta(minutes=5)


async def test_list_and_detail_timestamps_have_utc_offset(
    authenticated_client: httpx.AsyncClient,
):
    upload = await authenticated_client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files={"file": ("when.txt", b"x", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    file_id = upload.json()["id"]

    listing = await authenticated_client.get(f"{constants.ROUTE_PREFIX_API}{constants.PATH_FILES}")
    assert listing.status_code == 200
    _assert_utc(listing.json()["items"][0]["created_at"])

    detail = await authenticated_client.get(f"{constants.ROUTE_PREFIX_API}/files/{file_id}")
    assert detail.status_code == 200
    _assert_utc(detail.json()["created_at"])

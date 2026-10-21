"""The files JSON list rejects out-of-range paging with 422 (#513)."""

from __future__ import annotations

import httpx
import pytest
from file_storage import constants
from simple_module_db.pagination import MAX_PAGE, MAX_PER_PAGE

LIST_FILES = f"{constants.ROUTE_PREFIX_API}{constants.PATH_FILES}"


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -3},
        {"page": MAX_PAGE + 1},
        {"per_page": 0},
        {"per_page": MAX_PER_PAGE + 1},
    ],
)
async def test_rejects_out_of_range(params: dict, authenticated_client: httpx.AsyncClient) -> None:
    resp = await authenticated_client.get(LIST_FILES, params=params)
    assert resp.status_code == 422

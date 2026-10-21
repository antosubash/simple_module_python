"""The audit log JSON API rejects out-of-range paging with 422 (#513)."""

from __future__ import annotations

import httpx
import pytest
from simple_module_db.pagination import MAX_PAGE, MAX_PER_PAGE

LIST_URL = "/api/audit_log/"


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -3},
        {"page": MAX_PAGE + 1},
        {"page_size": 0},
        {"page_size": MAX_PER_PAGE + 1},
    ],
)
async def test_rejects_out_of_range(params: dict, authenticated_client: httpx.AsyncClient) -> None:
    resp = await authenticated_client.get(LIST_URL, params=params)
    assert resp.status_code == 422


async def test_accepts_max_page(authenticated_client: httpx.AsyncClient) -> None:
    resp = await authenticated_client.get(LIST_URL, params={"page": MAX_PAGE})
    assert resp.status_code == 200

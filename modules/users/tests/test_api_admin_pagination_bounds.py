"""``GET /api/users/admin`` validates paging like every other JSON list (#513)."""

from __future__ import annotations

import pytest
from simple_module_db.pagination import MAX_PAGE, MAX_PER_PAGE

ADMIN_URL = "/api/users/admin"


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -3},
        {"page": MAX_PAGE + 1},
        {"per_page": 0},
        {"per_page": -1},
        {"per_page": MAX_PER_PAGE + 1},
        {"per_page": 100000},
    ],
)
async def test_rejects_out_of_range(params: dict, admin_client, users_db) -> None:
    resp = await admin_client.get(ADMIN_URL, params=params)
    assert resp.status_code == 422


async def test_accepts_bounds(admin_client, users_db) -> None:
    resp = await admin_client.get(ADMIN_URL, params={"page": MAX_PAGE, "per_page": MAX_PER_PAGE})
    assert resp.status_code == 200
    assert resp.json() == []

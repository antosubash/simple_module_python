"""Consistent page/per_page bounds: JSON APIs reject (422), the outbox view clamps (#513)."""

from __future__ import annotations

import httpx
import pytest
from simple_module_db.pagination import MAX_PAGE, MAX_PER_PAGE

pytestmark = pytest.mark.usefixtures("_stub_celery")

EXECUTIONS_API = "/api/background_tasks/admin/executions"
OUTBOX_API = "/api/background_tasks/admin/outbox"
OUTBOX_VIEW = "/admin/background-tasks/outbox"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}

BAD_PARAMS = [
    {"page": 0},
    {"page": -3},
    {"page": MAX_PAGE + 1},
    {"per_page": 0},
    {"per_page": -1},
    {"per_page": MAX_PER_PAGE + 1},
]


@pytest.mark.parametrize("url", [EXECUTIONS_API, OUTBOX_API])
@pytest.mark.parametrize("params", BAD_PARAMS)
async def test_json_list_rejects_out_of_range(
    url: str, params: dict, authenticated_client: httpx.AsyncClient
) -> None:
    resp = await authenticated_client.get(url, params=params)
    assert resp.status_code == 422


@pytest.mark.parametrize("url", [EXECUTIONS_API, OUTBOX_API])
async def test_json_list_accepts_max_page(
    url: str, authenticated_client: httpx.AsyncClient
) -> None:
    resp = await authenticated_client.get(url, params={"page": MAX_PAGE})
    assert resp.status_code == 200


@pytest.mark.parametrize("page", ["0", "-3", "abc", str(MAX_PAGE + 1)])
async def test_outbox_view_clamps_instead_of_422(
    page: str, authenticated_client: httpx.AsyncClient
) -> None:
    resp = await authenticated_client.get(
        OUTBOX_VIEW, params={"page": page}, headers=INERTIA_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["props"]["pagination"]["page"] == 1

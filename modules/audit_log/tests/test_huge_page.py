"""qa F28: an absurd ``?page=`` must clamp, not overflow the driver into a 500."""

from __future__ import annotations

HUGE = "99999999999999999999"


async def test_view_with_huge_page_clamps(authenticated_client) -> None:
    resp = await authenticated_client.get(
        "/admin/audit-log/",
        params={"page": HUGE},
        headers={"X-Inertia": "true", "Accept": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["props"]["page"] == 1


async def test_api_with_huge_page_is_422(authenticated_client) -> None:
    resp = await authenticated_client.get("/api/audit_log/", params={"page": HUGE})
    # Past MAX_PAGE the strict dependency rejects it before any offset is built.
    assert resp.status_code == 422, resp.text

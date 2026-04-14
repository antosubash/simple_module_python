"""Permission boundary checks: viewer role denied on write, admin allowed.

Seeds data using the admin ``authenticated_client`` fixture, then asserts
403/302 responses from the ``viewer_client`` and an unauthenticated ``client``.
Both clients resolve the same ``app`` fixture per test, so they share the
in-memory database.
"""

from __future__ import annotations

import httpx


async def _seed_product(admin: httpx.AsyncClient, name: str = "Seed", price: str = "1.00") -> int:
    resp = await admin.post("/api/products/", json={"name": name, "price": price})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestViewerPermissions:
    async def test_viewer_can_list_products(
        self,
        authenticated_client: httpx.AsyncClient,
        viewer_client: httpx.AsyncClient,
    ):
        await _seed_product(authenticated_client, name="Visible")

        resp = await viewer_client.get("/api/products/")
        assert resp.status_code == 200
        assert [p["name"] for p in resp.json()] == ["Visible"]

    async def test_viewer_cannot_create_product(self, viewer_client: httpx.AsyncClient):
        resp = await viewer_client.post(
            "/api/products/",
            json={"name": "Forbidden", "price": "9.99"},
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_update_product(
        self,
        authenticated_client: httpx.AsyncClient,
        viewer_client: httpx.AsyncClient,
    ):
        product_id = await _seed_product(authenticated_client)

        resp = await viewer_client.put(
            f"/api/products/{product_id}",
            json={"name": "Hacked"},
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_delete_product(
        self,
        authenticated_client: httpx.AsyncClient,
        viewer_client: httpx.AsyncClient,
    ):
        product_id = await _seed_product(authenticated_client)

        resp = await viewer_client.delete(f"/api/products/{product_id}")
        assert resp.status_code == 403


class TestUnauthenticatedAccess:
    async def test_unauthenticated_api_redirects_to_login(self, client: httpx.AsyncClient):
        resp = await client.get("/api/products/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_unauthenticated_write_redirects_to_login(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/products/",
            json={"name": "Nope", "price": "1.00"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

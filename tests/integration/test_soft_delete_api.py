"""Soft-delete behaviour verified end-to-end through the HTTP API.

The service-level tests in ``modules/products/tests/test_products.py`` already
exercise ``ProductService`` directly; these tests assert that the same
semantics are exposed through ``/api/products/``.
"""

from __future__ import annotations

import httpx


async def _create(client: httpx.AsyncClient, name: str = "Target", price: str = "1.00") -> int:
    resp = await client.post("/api/products/", json={"name": name, "price": price})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestSoftDeleteOverHTTP:
    async def test_deleted_product_excluded_from_list(
        self, authenticated_client: httpx.AsyncClient
    ):
        product_id = await _create(authenticated_client)

        deleted = await authenticated_client.delete(f"/api/products/{product_id}")
        assert deleted.status_code == 204

        listing = await authenticated_client.get("/api/products/")
        assert listing.status_code == 200
        assert all(p["id"] != product_id for p in listing.json())

    async def test_deleted_product_returns_404_on_get(
        self, authenticated_client: httpx.AsyncClient
    ):
        product_id = await _create(authenticated_client)
        await authenticated_client.delete(f"/api/products/{product_id}")

        resp = await authenticated_client.get(f"/api/products/{product_id}")
        assert resp.status_code == 404

    async def test_deleted_product_returns_404_on_update(
        self, authenticated_client: httpx.AsyncClient
    ):
        product_id = await _create(authenticated_client)
        await authenticated_client.delete(f"/api/products/{product_id}")

        resp = await authenticated_client.put(
            f"/api/products/{product_id}",
            json={"name": "Revived"},
        )
        assert resp.status_code == 404

    async def test_second_delete_returns_404(self, authenticated_client: httpx.AsyncClient):
        product_id = await _create(authenticated_client)

        first = await authenticated_client.delete(f"/api/products/{product_id}")
        assert first.status_code == 204

        second = await authenticated_client.delete(f"/api/products/{product_id}")
        assert second.status_code == 404

    async def test_list_stays_empty_when_only_product_deleted(
        self, authenticated_client: httpx.AsyncClient
    ):
        product_id = await _create(authenticated_client, name="Only")
        await authenticated_client.delete(f"/api/products/{product_id}")

        listing = await authenticated_client.get("/api/products/")
        assert listing.status_code == 200
        assert listing.json() == []

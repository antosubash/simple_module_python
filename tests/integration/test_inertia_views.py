"""Integration tests for the Products Inertia view endpoints.

These exercise ``modules/products/products/endpoints/views.py``, which had
no direct test coverage. With the ``X-Inertia`` header Inertia returns JSON
of the shape ``{"component", "props", "url", "version"}``.
"""

from __future__ import annotations

import httpx


async def _seed_via_api(admin: httpx.AsyncClient, name: str, price: str = "1.00") -> int:
    resp = await admin.post("/api/products/", json={"name": name, "price": price})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestBrowseView:
    async def test_returns_inertia_page(self, inertia_client: httpx.AsyncClient):
        resp = await inertia_client.get("/products/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["component"] == "Products/Browse"
        assert body["props"]["pagination"]["perPage"] == 10
        assert body["props"]["pagination"]["page"] == 1
        assert body["props"]["products"] == []
        assert body["props"]["search"] == ""

    async def test_pagination_second_page(
        self,
        authenticated_client: httpx.AsyncClient,
        inertia_client: httpx.AsyncClient,
    ):
        # Seed 11 products so page 2 has exactly one product.
        for i in range(1, 12):
            await _seed_via_api(authenticated_client, name=f"P{i:02d}")

        first = await inertia_client.get("/products/?page=1")
        assert first.status_code == 200
        assert len(first.json()["props"]["products"]) == 10

        second = await inertia_client.get("/products/?page=2")
        assert second.status_code == 200
        props = second.json()["props"]
        assert len(props["products"]) == 1
        assert props["products"][0]["name"] == "P11"
        assert props["pagination"]["page"] == 2
        assert props["pagination"]["total"] == 11

    async def test_search_filter(
        self,
        authenticated_client: httpx.AsyncClient,
        inertia_client: httpx.AsyncClient,
    ):
        await _seed_via_api(authenticated_client, name="Alpha")
        await _seed_via_api(authenticated_client, name="Beta")

        resp = await inertia_client.get("/products/?q=Alph")
        assert resp.status_code == 200
        props = resp.json()["props"]
        assert [p["name"] for p in props["products"]] == ["Alpha"]
        assert props["search"] == "Alph"


class TestCreateView:
    async def test_renders_create_form(self, inertia_client: httpx.AsyncClient):
        resp = await inertia_client.get("/products/create")
        assert resp.status_code == 200
        assert resp.json()["component"] == "Products/Create"


class TestEditView:
    async def test_renders_for_existing_product(
        self,
        authenticated_client: httpx.AsyncClient,
        inertia_client: httpx.AsyncClient,
    ):
        product_id = await _seed_via_api(authenticated_client, name="Editable")

        resp = await inertia_client.get(f"/products/{product_id}/edit")
        assert resp.status_code == 200
        body = resp.json()
        assert body["component"] == "Products/Edit"
        assert body["props"]["product"]["id"] == product_id
        assert body["props"]["product"]["name"] == "Editable"

    async def test_missing_product_falls_back_to_browse_with_error(
        self, inertia_client: httpx.AsyncClient
    ):
        resp = await inertia_client.get("/products/9999/edit")
        assert resp.status_code == 200
        body = resp.json()
        assert body["component"] == "Products/Browse"
        assert body["props"]["error"] == "Product not found"


class TestCreateAction:
    async def test_valid_submission_redirects_to_listing(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.post(
            "/products/",
            json={"name": "Formed", "price": "2.50"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/products"

        listing = await authenticated_client.get("/api/products/")
        assert [p["name"] for p in listing.json()] == ["Formed"]

    async def test_invalid_submission_redirects_back(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.post(
            "/products/",
            json={"name": "", "price": "0"},
            headers={"referer": "/products/create"},
            follow_redirects=False,
        )
        # redirect_back_with_errors sends 303 to the referer.
        assert resp.status_code == 303
        assert resp.headers["location"] == "/products/create"


class TestUpdateAction:
    async def test_valid_update_redirects(
        self,
        authenticated_client: httpx.AsyncClient,
    ):
        product_id = await _seed_via_api(authenticated_client, name="Before")

        resp = await authenticated_client.put(
            f"/products/{product_id}",
            json={"name": "After"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/products"

        check = await authenticated_client.get(f"/api/products/{product_id}")
        assert check.status_code == 200
        assert check.json()["name"] == "After"


class TestDeleteAction:
    async def test_delete_redirects_and_removes_product(
        self,
        authenticated_client: httpx.AsyncClient,
    ):
        product_id = await _seed_via_api(authenticated_client, name="Doomed")

        resp = await authenticated_client.delete(
            f"/products/{product_id}", follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/products"

        check = await authenticated_client.get(f"/api/products/{product_id}")
        assert check.status_code == 404


class TestViewPermissions:
    async def test_viewer_cannot_post_create_action(self, viewer_client: httpx.AsyncClient):
        resp = await viewer_client.post(
            "/products/",
            json={"name": "Blocked", "price": "1.00"},
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_get_create_view(self, viewer_client: httpx.AsyncClient):
        resp = await viewer_client.get("/products/create")
        assert resp.status_code == 403

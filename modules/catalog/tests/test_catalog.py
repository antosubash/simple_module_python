"""Catalog list/search/filter/detail behaviour through the HTTP layer.

Seeding goes through ``app.state.sm.db.session_factory`` rather than the
``db_session`` fixture: those are two independent in-memory engines, so rows
written via ``db_session`` are invisible to requests made through the app.
"""

from __future__ import annotations

import uuid

import httpx
from catalog.constants import STATUS_ACTIVE, STATUS_DRAFT
from catalog.models import Category, Product

_OK = 200
_NOT_FOUND = 404
_UNAUTHORIZED = 401
_SEED_COUNT = 5
_ACTIVE_COUNT = 3


async def _seed(app) -> uuid.UUID:
    """Insert one category and five products; return the category id."""
    async with app.state.sm.db.session_factory() as session:
        category = Category(name="Widgets", slug="widgets")
        session.add(category)
        await session.flush()
        for i in range(_SEED_COUNT):
            session.add(
                Product(
                    sku=f"SKU-{i:03d}",
                    name=f"Widget {i}",
                    description="a test widget",
                    status=STATUS_ACTIVE if i % 2 == 0 else STATUS_DRAFT,
                    price_cents=100 * i,
                    category_id=category.id,
                )
            )
        await session.commit()
        return category.id


class TestCatalogListAPI:
    async def test_list_returns_paginated_products(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)
        resp = await authenticated_client.get("/api/catalog/products?page=1&page_size=2")
        assert resp.status_code == _OK
        body = resp.json()
        assert body["total"] == _SEED_COUNT
        assert len(body["items"]) == 2
        assert body["page"] == 1

    async def test_search_filters_by_name(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)
        resp = await authenticated_client.get("/api/catalog/products?q=Widget 3")
        assert resp.status_code == _OK
        assert [i["name"] for i in resp.json()["items"]] == ["Widget 3"]

    async def test_status_filter_narrows_results(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)
        resp = await authenticated_client.get(f"/api/catalog/products?status={STATUS_ACTIVE}")
        assert resp.status_code == _OK
        body = resp.json()
        assert body["total"] == _ACTIVE_COUNT
        assert all(i["status"] == STATUS_ACTIVE for i in body["items"])

    async def test_category_filter_narrows_results(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        category_id = await _seed(app)
        resp = await authenticated_client.get(f"/api/catalog/products?category_id={category_id}")
        assert resp.status_code == _OK
        assert resp.json()["total"] == _SEED_COUNT

    async def test_sort_by_name_orders_ascending(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)
        resp = await authenticated_client.get("/api/catalog/products?sort=name")
        names = [i["name"] for i in resp.json()["items"]]
        assert names == sorted(names)

    async def test_unknown_sort_falls_back_to_default(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """A bad sort key must not 500 or 422 — it falls back to newest-first."""
        await _seed(app)
        resp = await authenticated_client.get("/api/catalog/products?sort=bogus")
        assert resp.status_code == _OK
        assert resp.json()["total"] == _SEED_COUNT

    async def test_page_size_is_capped(self, app, authenticated_client: httpx.AsyncClient) -> None:
        await _seed(app)
        resp = await authenticated_client.get("/api/catalog/products?page_size=9999")
        assert resp.status_code == 422


class TestCatalogDetailAPI:
    async def test_detail_returns_single_product(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)
        listing = await authenticated_client.get("/api/catalog/products?page_size=1")
        product_id = listing.json()["items"][0]["id"]
        resp = await authenticated_client.get(f"/api/catalog/products/{product_id}")
        assert resp.status_code == _OK
        assert resp.json()["id"] == product_id

    async def test_detail_404s_for_unknown_id(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.get(f"/api/catalog/products/{uuid.uuid4()}")
        assert resp.status_code == _NOT_FOUND


class TestCatalogCategoriesAPI:
    async def test_lists_seeded_categories(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)
        resp = await authenticated_client.get("/api/catalog/categories")
        assert resp.status_code == _OK
        assert [c["slug"] for c in resp.json()] == ["widgets"]


class TestCatalogAuth:
    async def test_list_requires_authentication(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/catalog/products")
        assert resp.status_code == _UNAUTHORIZED


class TestCatalogViews:
    async def test_browse_renders_the_inertia_page(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)
        resp = await authenticated_client.get(
            "/catalog/", headers={"X-Inertia": "true", "Accept": "application/json"}
        )
        assert resp.status_code == _OK
        body = resp.json()
        assert body["component"] == "Catalog/Browse"
        assert body["props"]["total"] == _SEED_COUNT

    async def test_browse_survives_a_garbage_query_string(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Bad pagination params fall back to defaults instead of 422ing."""
        await _seed(app)
        resp = await authenticated_client.get(
            "/catalog/?page=abc&page_size=xyz&status=nope&sort=nope",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == _OK
        assert resp.json()["props"]["page"] == 1

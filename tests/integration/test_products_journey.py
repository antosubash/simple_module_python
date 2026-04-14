"""Cross-module user journeys for the Products API.

Exercises the full request path (session middleware → auth → permission
registry → router → service → SQLAlchemy listeners) against a fresh
in-memory app per test.
"""

from __future__ import annotations

import httpx


class TestProductLifecycle:
    async def test_full_product_lifecycle(self, authenticated_client: httpx.AsyncClient):
        create = await authenticated_client.post(
            "/api/products/",
            json={"name": "Widget", "description": "useful", "price": "19.99"},
        )
        assert create.status_code == 201
        product_id = create.json()["id"]

        listing = await authenticated_client.get("/api/products/")
        assert listing.status_code == 200
        ids = [p["id"] for p in listing.json()]
        assert product_id in ids

        fetch = await authenticated_client.get(f"/api/products/{product_id}")
        assert fetch.status_code == 200
        assert fetch.json()["name"] == "Widget"

        update = await authenticated_client.put(
            f"/api/products/{product_id}",
            json={"name": "Widget v2", "price": "29.99"},
        )
        assert update.status_code == 200
        assert update.json()["name"] == "Widget v2"
        assert update.json()["price"] == "29.99"

        deleted = await authenticated_client.delete(f"/api/products/{product_id}")
        assert deleted.status_code == 204

        missing = await authenticated_client.get(f"/api/products/{product_id}")
        assert missing.status_code == 404

        final = await authenticated_client.get("/api/products/")
        assert final.status_code == 200
        assert all(p["id"] != product_id for p in final.json())

    async def test_multiple_products_listed_in_order(
        self, authenticated_client: httpx.AsyncClient
    ):
        names = ["Alpha", "Beta", "Gamma"]
        ids = []
        for name in names:
            resp = await authenticated_client.post(
                "/api/products/",
                json={"name": name, "price": "1.00"},
            )
            assert resp.status_code == 201
            ids.append(resp.json()["id"])

        listing = await authenticated_client.get("/api/products/")
        assert listing.status_code == 200
        assert [p["id"] for p in listing.json()] == ids
        assert [p["name"] for p in listing.json()] == names


class TestSessionDuringJourney:
    async def test_session_user_visible_before_and_after_crud(
        self, authenticated_client: httpx.AsyncClient
    ):
        before = await authenticated_client.get("/auth/me")
        assert before.status_code == 200
        assert before.json() == {
            "authenticated": True,
            "user": {
                "sub": "test-user-id",
                "email": "test@example.com",
                "name": "Test User",
                "preferred_username": "testuser",
                "realm_access": {"roles": ["admin"]},
            },
        }

        create = await authenticated_client.post(
            "/api/products/", json={"name": "Journey", "price": "5.00"}
        )
        assert create.status_code == 201

        after = await authenticated_client.get("/auth/me")
        assert after.status_code == 200
        assert after.json()["authenticated"] is True
        assert after.json()["user"]["sub"] == "test-user-id"

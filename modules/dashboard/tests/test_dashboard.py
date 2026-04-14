"""Tests for the Dashboard module: event handlers, stats endpoint, and
end-to-end event-bus wiring between Products and Dashboard."""

from __future__ import annotations

import httpx
import pytest
from simple_module_core.events import EventBus
from sm_dashboard.handlers import (
    get_product_event_counts,
    on_product_created,
    on_product_deleted,
    on_product_updated,
    reset_product_event_counts,
)
from sm_dashboard.module import DashboardModule
from sm_products.contracts.events import ProductCreated, ProductDeleted, ProductUpdated


@pytest.fixture(autouse=True)
def _reset_counts():
    """Ensure every test starts with zeroed product event counters."""
    reset_product_event_counts()
    yield
    reset_product_event_counts()


# ── Handler unit tests ───────────────────────────────────────────────


class TestDashboardHandlers:
    async def test_on_product_created_increments_counter(self):
        await on_product_created(ProductCreated(product_id=1, name="Widget"))
        counts = get_product_event_counts()
        assert counts["created"] == 1
        assert counts["updated"] == 0
        assert counts["deleted"] == 0

    async def test_on_product_updated_increments_counter(self):
        await on_product_updated(ProductUpdated(product_id=1, name="Widget"))
        counts = get_product_event_counts()
        assert counts["updated"] == 1
        assert counts["created"] == 0

    async def test_on_product_deleted_increments_counter(self):
        await on_product_deleted(ProductDeleted(product_id=1))
        counts = get_product_event_counts()
        assert counts["deleted"] == 1

    async def test_multiple_events_accumulate(self):
        await on_product_created(ProductCreated(product_id=1, name="A"))
        await on_product_created(ProductCreated(product_id=2, name="B"))
        await on_product_updated(ProductUpdated(product_id=1, name="A2"))
        counts = get_product_event_counts()
        assert counts["created"] == 2
        assert counts["updated"] == 1
        assert counts["deleted"] == 0

    async def test_get_product_event_counts_returns_snapshot(self):
        """Returned dict should be a copy, not the internal store."""
        counts = get_product_event_counts()
        counts["created"] = 999
        # Mutating returned dict should not affect internal state
        assert get_product_event_counts()["created"] == 0

    async def test_reset_clears_all_counts(self):
        await on_product_created(ProductCreated(product_id=1, name="X"))
        await on_product_deleted(ProductDeleted(product_id=1))
        reset_product_event_counts()
        counts = get_product_event_counts()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}


# ── Module registration tests ────────────────────────────────────────


class TestDashboardModuleRegistration:
    async def test_module_meta(self):
        mod = DashboardModule()
        assert mod.meta.name == "Dashboard"
        assert mod.meta.route_prefix == "/api/dashboard"
        assert "Products" in mod.meta.depends_on

    async def test_register_event_handlers_subscribes_to_all_product_events(self):
        """DashboardModule should wire handlers for all three product events."""
        bus = EventBus()
        mod = DashboardModule()
        mod.register_event_handlers(bus)

        # Publishing each event should update the counters via the subscribed handler.
        await bus.publish(ProductCreated(product_id=1, name="Widget"))
        await bus.publish(ProductUpdated(product_id=1, name="Widget v2"))
        await bus.publish(ProductDeleted(product_id=1))

        counts = get_product_event_counts()
        assert counts == {"created": 1, "updated": 1, "deleted": 1}


# ── Stats API endpoint ──────────────────────────────────────────────


class TestDashboardStatsEndpoint:
    async def test_stats_returns_zero_counts_initially(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"product_events": {"created": 0, "updated": 0, "deleted": 0}}

    async def test_stats_reflects_handler_activity(
        self, authenticated_client: httpx.AsyncClient
    ):
        await on_product_created(ProductCreated(product_id=1, name="X"))
        await on_product_updated(ProductUpdated(product_id=1, name="X"))

        resp = await authenticated_client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["product_events"]["created"] == 1
        assert body["product_events"]["updated"] == 1
        assert body["product_events"]["deleted"] == 0

    async def test_stats_requires_authentication(self, client: httpx.AsyncClient):
        """Unauthenticated requests should be redirected by AuthMiddleware."""
        resp = await client.get("/api/dashboard/stats", follow_redirects=False)
        assert resp.status_code in (302, 401, 403)


# ── End-to-end: Product API → EventBus → Dashboard handler ──────────


class TestProductEventIntegration:
    """Prove the modules actually communicate through the event bus."""

    async def test_create_product_increments_dashboard_counter(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.post(
            "/api/products/",
            json={"name": "EventTestWidget", "price": "12.34"},
        )
        assert resp.status_code == 201

        stats = await authenticated_client.get("/api/dashboard/stats")
        assert stats.json()["product_events"]["created"] == 1

    async def test_update_product_increments_dashboard_counter(
        self, authenticated_client: httpx.AsyncClient
    ):
        create = await authenticated_client.post(
            "/api/products/",
            json={"name": "Original", "price": "1.00"},
        )
        product_id = create.json()["id"]
        reset_product_event_counts()  # isolate the update count

        resp = await authenticated_client.put(
            f"/api/products/{product_id}",
            json={"name": "Updated"},
        )
        assert resp.status_code == 200

        stats = await authenticated_client.get("/api/dashboard/stats")
        assert stats.json()["product_events"]["updated"] == 1

    async def test_delete_product_increments_dashboard_counter(
        self, authenticated_client: httpx.AsyncClient
    ):
        create = await authenticated_client.post(
            "/api/products/",
            json={"name": "Doomed", "price": "1.00"},
        )
        product_id = create.json()["id"]
        reset_product_event_counts()

        resp = await authenticated_client.delete(f"/api/products/{product_id}")
        assert resp.status_code == 204

        stats = await authenticated_client.get("/api/dashboard/stats")
        assert stats.json()["product_events"]["deleted"] == 1

    async def test_failed_update_does_not_emit_event(
        self, authenticated_client: httpx.AsyncClient
    ):
        """404s should not publish ProductUpdated — handler logic must be after the lookup."""
        resp = await authenticated_client.put(
            "/api/products/999999",
            json={"name": "ghost"},
        )
        assert resp.status_code == 404

        stats = await authenticated_client.get("/api/dashboard/stats")
        assert stats.json()["product_events"]["updated"] == 0

    async def test_failed_delete_does_not_emit_event(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.delete("/api/products/999999")
        assert resp.status_code == 404

        stats = await authenticated_client.get("/api/dashboard/stats")
        assert stats.json()["product_events"]["deleted"] == 0

    async def test_full_lifecycle_counters(self, authenticated_client: httpx.AsyncClient):
        """Create → update → delete should all increment their respective counters."""
        create = await authenticated_client.post(
            "/api/products/",
            json={"name": "Lifecycle", "price": "1.00"},
        )
        pid = create.json()["id"]
        await authenticated_client.put(f"/api/products/{pid}", json={"name": "L2"})
        await authenticated_client.delete(f"/api/products/{pid}")

        stats = await authenticated_client.get("/api/dashboard/stats")
        counts = stats.json()["product_events"]
        assert counts == {"created": 1, "updated": 1, "deleted": 1}

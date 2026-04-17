"""Tests for the Products module: service CRUD, API endpoints, schema validation."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from products.contracts.schemas import ProductCreate, ProductUpdate
from products.service import ProductService
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

# ── Model index guards ───────────────────────────────────────────────


def _has_index_on(model, column_name: str) -> bool:
    """Check that the model's table has an index covering the given column."""
    table = model.__table__
    return any(column_name in {c.name for c in idx.columns} for idx in table.indexes)


class TestProductModelIndexes:
    def test_is_deleted_is_indexed(self):
        from products.models import Product

        assert _has_index_on(Product, "is_deleted"), (
            "Product.is_deleted must be indexed — it's the primary filter on the "
            "public listing query and the planner can use the index to skip "
            "tombstoned rows cheaply."
        )

    def test_is_active_is_not_indexed(self):
        """``is_active`` is intentionally un-indexed — a plain B-tree over a
        2-value boolean is rarely preferred by the planner and wastes writes."""
        from products.models import Product

        assert not _has_index_on(Product, "is_active"), (
            "Product.is_active should not be indexed — drop the index if you "
            "reintroduce it by mistake."
        )


# ── Schema validation ────────────────────────────────────────────────


class TestProductSchemas:
    async def test_product_create_valid(self):
        data = ProductCreate(name="Widget", price=Decimal("9.99"))
        assert data.name == "Widget"
        assert data.price == Decimal("9.99")
        assert data.description is None

    async def test_product_create_with_description(self):
        data = ProductCreate(name="Widget", description="A fine widget", price=Decimal("9.99"))
        assert data.description == "A fine widget"

    async def test_product_create_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            ProductCreate(name="", price=Decimal("9.99"))

    async def test_product_create_zero_price_rejected(self):
        with pytest.raises(ValidationError):
            ProductCreate(name="Widget", price=Decimal("0"))

    async def test_product_create_negative_price_rejected(self):
        with pytest.raises(ValidationError):
            ProductCreate(name="Widget", price=Decimal("-1.00"))

    async def test_product_update_all_optional(self):
        data = ProductUpdate()
        assert data.name is None
        assert data.price is None
        assert data.is_active is None


# ── ProductService CRUD ──────────────────────────────────────────────


class TestProductService:
    async def test_create(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        product = await svc.create(ProductCreate(name="Widget", price=Decimal("19.99")))
        assert product.id is not None
        assert product.name == "Widget"
        assert product.price == Decimal("19.99")
        assert product.is_active is True

    async def test_get_all(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        await svc.create(ProductCreate(name="A", price=Decimal("1.00")))
        await svc.create(ProductCreate(name="B", price=Decimal("2.00")))
        products = await svc.get_all()
        assert len(products) == 2

    async def test_get_by_id(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        created = await svc.create(ProductCreate(name="X", price=Decimal("5.00")))
        found = await svc.get_by_id(created.id)
        assert found is not None
        assert found.name == "X"

    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        found = await svc.get_by_id(999)
        assert found is None

    async def test_update(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        created = await svc.create(ProductCreate(name="Old", price=Decimal("10.00")))
        updated = await svc.update(created.id, ProductUpdate(name="New"))
        assert updated is not None
        assert updated.name == "New"
        assert updated.price == Decimal("10.00")  # unchanged

    async def test_update_not_found(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        result = await svc.update(999, ProductUpdate(name="Ghost"))
        assert result is None

    async def test_delete(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        created = await svc.create(ProductCreate(name="Doomed", price=Decimal("1.00")))
        deleted = await svc.delete(created.id)
        assert deleted is True

    async def test_delete_not_found(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        deleted = await svc.delete(999)
        assert deleted is False

    async def test_soft_deleted_excluded_from_get_all(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        created = await svc.create(ProductCreate(name="Temp", price=Decimal("1.00")))
        await svc.delete(created.id)
        await db_session.flush()
        products, _total = await svc.get_all()
        assert all(p.id != created.id for p in products)

    async def test_soft_deleted_excluded_from_get_by_id(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        created = await svc.create(ProductCreate(name="Ghost", price=Decimal("1.00")))
        await svc.delete(created.id)
        await db_session.flush()
        found = await svc.get_by_id(created.id)
        assert found is None

    async def test_soft_deleted_cannot_be_updated(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        created = await svc.create(ProductCreate(name="Old", price=Decimal("1.00")))
        await svc.delete(created.id)
        await db_session.flush()
        result = await svc.update(created.id, ProductUpdate(name="New"))
        assert result is None

    async def test_soft_deleted_cannot_be_deleted_again(self, db_session: AsyncSession):
        svc = ProductService(db_session)
        created = await svc.create(ProductCreate(name="Once", price=Decimal("1.00")))
        await svc.delete(created.id)
        await db_session.flush()
        deleted_again = await svc.delete(created.id)
        assert deleted_again is False


# ── Products API endpoints ───────────────────────────────────────────


class TestProductsAPI:
    async def test_list_products_empty(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/products/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_product(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(
            "/api/products/",
            json={"name": "Test Product", "price": "29.99"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Product"
        assert data["id"] is not None

    async def test_get_product_by_id(self, authenticated_client: httpx.AsyncClient):
        create_resp = await authenticated_client.post(
            "/api/products/",
            json={"name": "Findable", "price": "5.00"},
        )
        product_id = create_resp.json()["id"]

        resp = await authenticated_client.get(f"/api/products/{product_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Findable"

    async def test_get_product_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/products/99999")
        assert resp.status_code == 404

    async def test_update_product(self, authenticated_client: httpx.AsyncClient):
        create_resp = await authenticated_client.post(
            "/api/products/",
            json={"name": "Original", "price": "10.00"},
        )
        product_id = create_resp.json()["id"]

        resp = await authenticated_client.put(
            f"/api/products/{product_id}",
            json={"name": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    async def test_delete_product(self, authenticated_client: httpx.AsyncClient):
        create_resp = await authenticated_client.post(
            "/api/products/",
            json={"name": "Deletable", "price": "1.00"},
        )
        product_id = create_resp.json()["id"]

        resp = await authenticated_client.delete(f"/api/products/{product_id}")
        assert resp.status_code == 204

    async def test_delete_product_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.delete("/api/products/99999")
        assert resp.status_code == 404

    async def test_create_product_invalid_data(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(
            "/api/products/",
            json={"name": "", "price": "0"},
        )
        assert resp.status_code == 422  # Validation error


# ── Module lifecycle ────────────────────────────────────────────────


class TestProductsModuleLifecycle:
    async def test_on_startup_does_not_call_create_all(self):
        """on_startup should not create tables — Alembic manages schema."""
        from unittest.mock import AsyncMock, MagicMock

        from products.module import ProductsModule

        mod = ProductsModule()
        mock_app = MagicMock()
        mock_app.state.sm.db.engine = AsyncMock()

        await mod.on_startup(mock_app)

        # Engine should not have been used for DDL
        mock_app.state.sm.db.engine.begin.assert_not_called()

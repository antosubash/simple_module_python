"""Table shape and mixin wiring for the Catalog models."""

from __future__ import annotations

from catalog.constants import TABLE_CATEGORY, TABLE_PRODUCT
from catalog.models import Category, Product


def test_tables_are_module_prefixed() -> None:
    assert Category.__tablename__ == TABLE_CATEGORY
    assert Product.__tablename__ == TABLE_PRODUCT
    assert TABLE_CATEGORY.startswith("catalog_")
    assert TABLE_PRODUCT.startswith("catalog_")


def test_product_carries_audit_and_soft_delete_columns() -> None:
    columns = set(Product.__table__.columns.keys())
    assert {"created_at", "updated_at", "created_by", "updated_by"} <= columns
    assert {"is_deleted", "deleted_at", "deleted_by"} <= columns


def test_product_has_indexes_for_search_and_listing() -> None:
    index_names = {ix.name for ix in Product.__table__.indexes}
    assert "ix_catalog_product_name" in index_names
    assert "ix_catalog_product_status_created_at" in index_names
    assert "ix_catalog_product_category_id" in index_names


def test_product_category_fk_targets_category_table() -> None:
    fk = next(iter(Product.__table__.c.category_id.foreign_keys))
    assert fk.column.table.name == TABLE_CATEGORY

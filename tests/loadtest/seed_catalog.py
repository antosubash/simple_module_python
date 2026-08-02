"""Seed catalog products (faker) into the load-test database.

Bulk-inserts categories and products so the catalog list/search/sort endpoints
are exercised against realistic volumes — single-row tables hide the missing
indexes and serialization costs that matter under load.

Kept separate from ``seed.py`` (users + audit) so each seed stays runnable on
its own and neither file approaches the repo's 300-line cap.

Run from the repo root against a THROWAWAY database (never your dev DB):

    SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/smpy_loadtest \\
      uv run python tests/loadtest/seed_catalog.py [n_products] [--force]

Or via ``make loadtest-seed-catalog``. Default: 5000 products, 12 categories.
Idempotent — skips if the marker product already exists; ``--force`` wipes
prior seeded rows and re-seeds.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

from catalog.constants import STATUS_VALUES
from catalog.models import Category, Product
from faker import Faker
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import create_async_engine

MARKER_SKU = "LOADTEST-0000"
SKU_PREFIX = "LOADTEST-"
CATEGORY_SLUG_PREFIX = "loadtest-category-"
N_CATEGORIES = 12
BATCH_SIZE = 1000
DEFAULT_PRODUCTS = 5_000
PRICE_STEP_CENTS = 137
MAX_PRICE_CENTS = 500_000
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

fake = Faker()
Faker.seed(42)


def _int_arg(idx: int, default: int) -> int:
    args = [a for a in sys.argv[1:] if a.isdigit()]
    return int(args[idx]) if len(args) > idx else default


def _category_rows() -> list[dict]:
    return [
        {
            "id": uuid.uuid4(),
            "name": f"Category {i:02d}",
            "slug": f"{CATEGORY_SLUG_PREFIX}{i:02d}",
            "created_at": NOW,
            "updated_at": None,
            "created_by": None,
            "updated_by": None,
        }
        for i in range(N_CATEGORIES)
    ]


def _product_row(i: int, category_ids: list[uuid.UUID]) -> dict:
    return {
        "id": uuid.uuid4(),
        "sku": f"{SKU_PREFIX}{i:04d}",
        "name": fake.catch_phrase(),
        "description": fake.sentence(nb_words=12),
        "status": STATUS_VALUES[i % len(STATUS_VALUES)],
        "price_cents": (i * PRICE_STEP_CENTS) % MAX_PRICE_CENTS,
        "category_id": category_ids[i % len(category_ids)],
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
        # Spread created_at so the default (created DESC) ordering and the
        # composite (status, created_at) index both see realistic spread.
        "created_at": NOW - timedelta(minutes=i),
        "updated_at": None,
        "created_by": None,
        "updated_by": None,
    }


async def main() -> None:
    db_url = os.environ.get("SM_DATABASE_URL")
    if not db_url:
        raise SystemExit("set SM_DATABASE_URL to your throwaway load-test database first")
    n_products = _int_arg(0, DEFAULT_PRODUCTS)
    force = "--force" in sys.argv

    engine = create_async_engine(db_url, pool_size=5, max_overflow=10)

    async with engine.begin() as conn:
        marker = (await conn.execute(select(Product.id).where(Product.sku == MARKER_SKU))).first()
        if marker and not force:
            total = (await conn.execute(select(func.count()).select_from(Product))).scalar()
            print(f"already seeded (products={total}); pass --force to re-seed")
            await engine.dispose()
            return
        if force:
            # Scope every delete to seeded rows — never truncate a table
            # wholesale, so an accidental --force against a shared DB cannot
            # wipe real data. Products first: they FK to categories.
            await conn.execute(delete(Product).where(Product.sku.like(f"{SKU_PREFIX}%")))
            await conn.execute(
                delete(Category).where(Category.slug.like(f"{CATEGORY_SLUG_PREFIX}%"))
            )

        categories = _category_rows()
        await conn.execute(Category.__table__.insert(), categories)
        category_ids = [c["id"] for c in categories]

        print(f"seeding {n_products} products ...")
        batch: list[dict] = []
        for i in range(n_products):
            batch.append(_product_row(i, category_ids))
            if len(batch) >= BATCH_SIZE:
                await conn.execute(Product.__table__.insert(), batch)
                batch = []
        if batch:
            await conn.execute(Product.__table__.insert(), batch)

        print(f"seeded {n_products} products across {N_CATEGORIES} categories")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

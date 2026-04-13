"""Event handlers for the Dashboard module.

Subscribes to product domain events to maintain real-time stats
without direct coupling to the Products module's internals.
"""

from __future__ import annotations

import logging

from sm_products.contracts.events import ProductCreated, ProductDeleted, ProductUpdated

logger = logging.getLogger(__name__)

_product_event_counts: dict[str, int] = {
    "created": 0,
    "updated": 0,
    "deleted": 0,
}


async def on_product_created(event: ProductCreated) -> None:
    _product_event_counts["created"] += 1
    logger.info("Dashboard received ProductCreated: %s (id=%d)", event.name, event.product_id)


async def on_product_updated(event: ProductUpdated) -> None:
    _product_event_counts["updated"] += 1
    logger.info("Dashboard received ProductUpdated: %s (id=%d)", event.name, event.product_id)


async def on_product_deleted(event: ProductDeleted) -> None:
    _product_event_counts["deleted"] += 1
    logger.info("Dashboard received ProductDeleted: id=%d", event.product_id)


def get_product_event_counts() -> dict[str, int]:
    """Return a snapshot of product event counts."""
    return dict(_product_event_counts)


def reset_product_event_counts() -> None:
    """Reset counters — useful for testing."""
    _product_event_counts["created"] = 0
    _product_event_counts["updated"] = 0
    _product_event_counts["deleted"] = 0

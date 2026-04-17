"""FastAPI dependencies for the Products module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.events import EventBus
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from products.service import ProductService


async def get_product_service(
    db: AsyncSession = Depends(get_db),
) -> ProductService:
    return ProductService(db)


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.sm.event_bus

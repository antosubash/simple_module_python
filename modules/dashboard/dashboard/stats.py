"""Dashboard statistics queries."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from products.models import Product
from simple_module_core.discovery import discover_modules
from simple_module_core.health import HealthStatus
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from users.models import User


async def fetch_dashboard_stats(db: AsyncSession, app: FastAPI) -> dict:
    """Gather all dashboard statistics in a single call."""
    total_users = await _count_users(db)
    active_users_7d = await _count_active_users(db, days=7)
    total_products = await _count_products(db)
    module_count, modules_list = _get_module_info()
    health_checks = await _run_health_checks(app)

    return {
        "total_users": total_users,
        "active_users_7d": active_users_7d,
        "total_products": total_products,
        "module_count": module_count,
        "system_info": {
            "modules": modules_list,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "health_checks": health_checks,
        },
    }


async def _count_users(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def _count_active_users(db: AsyncSession, *, days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(func.count()).select_from(User).where(User.last_login_at >= cutoff)
    )
    return result.scalar_one()


async def _count_products(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(Product).where(Product.is_active.is_(True))
    )
    return result.scalar_one()


def _get_module_info() -> tuple[int, list[dict[str, str]]]:
    modules = discover_modules()
    modules_list = [{"name": m.meta.name, "status": "loaded"} for m in modules]
    return len(modules), modules_list


async def _run_health_checks(app: FastAPI) -> list[dict[str, str]]:
    registry = app.state.health_registry
    results = []
    for check in registry.all_checks:
        try:
            result = await check.check()
            results.append({"name": check.name, "status": result.status.value})
        except Exception:
            results.append({"name": check.name, "status": HealthStatus.UNHEALTHY.value})
    return results

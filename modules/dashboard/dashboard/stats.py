"""Dashboard statistics queries with TTL-based caching."""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from products.models import Product
from simple_module_core.health import HealthCheck, HealthStatus
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from users.models import User

_CACHE_TTL_SECONDS = 30
_cache: dict | None = None
_cache_ts: float = 0.0
_cache_lock = asyncio.Lock()


def _cache_hit() -> dict | None:
    if _cache is not None and (time.monotonic() - _cache_ts) < _CACHE_TTL_SECONDS:
        return _cache.copy()
    return None


async def fetch_dashboard_stats(db: AsyncSession, app: FastAPI) -> dict:
    """Gather all dashboard statistics, cached for 30 seconds."""
    global _cache, _cache_ts

    hit = _cache_hit()
    if hit is not None:
        return hit

    async with _cache_lock:
        # Re-check after acquiring lock — another coroutine may have refreshed.
        hit = _cache_hit()
        if hit is not None:
            return hit

        total_users = await _count_users(db)
        active_users_7d = await _count_active_users(db, days=7)
        total_products = await _count_products(db)
        modules_list = _get_module_info(app)
        health_checks = await _run_health_checks(app)

        result = {
            "total_users": total_users,
            "active_users_7d": active_users_7d,
            "total_products": total_products,
            "module_count": len(modules_list),
            "system_info": {
                "modules": modules_list,
                "python_version": (
                    f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
                ),
                "health_checks": health_checks,
            },
        }

        _cache = result
        _cache_ts = time.monotonic()
        return result.copy()


def invalidate_stats_cache() -> None:
    """Clear the stats cache — useful for testing or after data mutations."""
    global _cache, _cache_ts
    _cache = None
    _cache_ts = 0.0


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


def _get_module_info(app: FastAPI) -> list[dict[str, str]]:
    # Reads from the module list discovered once at startup, avoiding
    # expensive entry-point rescans on every request.
    modules = getattr(app.state, "modules", None)
    if modules is None:
        return []
    return [{"name": m.meta.name, "status": "loaded"} for m in modules]


async def _run_health_checks(app: FastAPI) -> list[dict[str, str]]:
    registry = app.state.health_registry
    checks = registry.all_checks
    if not checks:
        return []

    async def _run_one(check: HealthCheck) -> dict[str, str]:
        try:
            result = await check.check()
            return {"name": check.name, "status": result.status.value}
        except Exception:
            return {"name": check.name, "status": HealthStatus.UNHEALTHY.value}

    return list(await asyncio.gather(*[_run_one(c) for c in checks]))

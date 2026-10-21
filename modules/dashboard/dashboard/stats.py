"""Dashboard statistics queries with TTL-based caching."""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import timedelta

from fastapi import FastAPI
from simple_module_core.discovery import get_module_package_name
from simple_module_core.health import HealthCheck, HealthStatus
from simple_module_core.user_directory import get_user_directory
from sqlalchemy.ext.asyncio import AsyncSession

_CACHE_TTL_SECONDS = 30
_ACTIVE_WINDOW_DAYS = 7
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

        # Counted by whichever auth provider holds the accounts (GH #501); a
        # ``None`` is a figure it cannot give, and the page hides that tile.
        user_stats = await get_user_directory(app).stats(
            db, active_window=timedelta(days=_ACTIVE_WINDOW_DAYS)
        )
        health_checks = await _run_health_checks(app)
        modules_list = _get_module_info(app, health_checks)

        result = {
            "total_users": user_stats.total,
            "active_users_7d": user_stats.active_since,
            "users_created_this_month": user_stats.created_this_month,
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


# Worst-first: a module's tile reports the worst state among its checks, so a
# single unhealthy check is never hidden behind a healthy sibling.
_HEALTH_SEVERITY = {
    HealthStatus.HEALTHY.value: 0,
    HealthStatus.DEGRADED.value: 1,
    HealthStatus.UNHEALTHY.value: 2,
}


def _get_module_info(app: FastAPI, health_checks: list[dict[str, str]]) -> list[dict[str, str]]:
    # Reads from the module list discovered once at startup, avoiding
    # expensive entry-point rescans on every request.
    worst: dict[str, str] = {}
    for check in health_checks:
        owner = check.get("module") or ""
        if not owner:
            continue
        current = worst.get(owner)
        if current is None or _HEALTH_SEVERITY.get(check["status"], 0) > _HEALTH_SEVERITY.get(
            current, 0
        ):
            worst[owner] = check["status"]

    # `url` is the module's own screen. It is deliberately NOT filtered by the
    # caller's permissions here: this whole payload is process-wide cached for
    # 30s, so anything user-specific would leak across sessions. The page gates
    # each link against the per-user `menus` prop instead.
    prefixes = app.state.sm.view_prefixes
    return [
        {
            "name": m.meta.name,
            # The deck's tiles are labelled with the package directory
            # (``audit_log``), not the display name (``AuditLog``) — they sit
            # in a mono face and read as the thing you would `uv add`.
            "package": get_module_package_name(m),
            "status": "loaded",
            "url": f"{prefixes[m.meta.name]}/" if m.meta.name in prefixes else "",
            # A partly-administrative module (users) mounts its management
            # screens outside its own view_prefix, so the tile cannot find
            # them by prefix alone — ship the second mount point too.
            "admin_url": (f"{m.meta.admin_view_prefix}/" if m.meta.admin_view_prefix else ""),
            "health": worst.get(m.meta.name, ""),
        }
        for m in app.state.sm.modules
    ]


async def _run_health_checks(app: FastAPI) -> list[dict[str, str]]:
    registry = app.state.sm.health_registry
    # Same reasoning as the readiness probe: this runs on every dashboard load
    # (behind a 30s cache), which is still far too often to be authenticating
    # against a mail provider. Modules whose only checks are on-demand simply
    # report no health on their tile, which is honest — nothing is watching.
    checks = registry.probe_checks
    if not checks:
        return []

    async def _run_one(check: HealthCheck) -> dict[str, str]:
        try:
            result = await check.check()
            return {"name": check.name, "status": result.status.value, "module": check.module}
        except Exception:
            return {
                "name": check.name,
                "status": HealthStatus.UNHEALTHY.value,
                "module": check.module,
            }

    return list(await asyncio.gather(*[_run_one(c) for c in checks]))

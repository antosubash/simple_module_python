"""Run a module's connection checks on demand, for the view and the API alike."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, status

from settings.module_settings.discovery import _package_of


async def run_connection_test(app: FastAPI, package: str) -> dict[str, Any]:
    """Run one module's health checks now and report each result.

    Returns the per-check results even when a check fails: an admin testing a
    connection expects to read the failure, not an error status with the reason
    buried. Raises 404 for an unknown package or one with nothing to test.
    """
    modules = getattr(app.state.sm, "modules", ())
    owner = next((m for m in modules if _package_of(m) == package), None)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown module package: {package}"
        )

    checks = [c for c in app.state.sm.health_registry.all_checks if c.module == owner.meta.name]
    if not checks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{owner.meta.name} has no connection to test",
        )

    # Run independently of one another: a module can register several checks
    # (e.g. SMTP + primary storage + backup storage), and awaiting each in turn
    # would block for the sum of their latencies instead of the slowest one.
    async def _run_one(check) -> dict[str, Any]:
        try:
            outcome = await check.check()
            return {
                "name": check.name,
                "status": outcome.status.value,
                "detail": outcome.detail or "",
            }
        except Exception as exc:
            return {"name": check.name, "status": "unhealthy", "detail": str(exc)}

    results = await asyncio.gather(*[_run_one(c) for c in checks])
    return {"module": owner.meta.name, "checks": results}

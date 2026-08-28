"""What the setup wizard displays.

Split from ``routes_setup`` so that module holds the routes and the gating that
guards them, while this one holds the read-only shaping of what the page
renders. They change for different reasons: a new dependency to probe touches
this file, a new security condition touches that one.
"""

from __future__ import annotations

import asyncio

from fastapi import Request

CHECK_DATABASE = "host.database"
CHECK_REDIS = "background_tasks.redis"


async def run_check(request: Request, name: str) -> dict | None:
    """Run one registered health check by name and shape it for the UI.

    ``None`` when nothing registered that name — an install without the
    background_tasks module has no Redis to reach, and listing it as a failed
    connection would send an operator hunting for a service they don't run.
    """
    registry = request.app.state.sm.health_registry
    for check in registry.all_checks:
        if check.name != name:
            continue
        result = await check.check()
        return {
            "name": name,
            "status": str(result.status),
            # The reason is the point: "connection refused" and "authentication
            # failed" need different fixes.
            "detail": result.detail or "",
        }
    return None


async def connection_status(request: Request) -> list[dict]:
    """Every dependency this install actually has, probed concurrently.

    Concurrently because each probe carries its own connect timeout: run in
    series, a wizard on a host where both the database and Redis are
    unreachable waits for the sum of them before rendering anything, which is
    exactly the case the wizard exists to diagnose.
    """
    results = await asyncio.gather(
        run_check(request, CHECK_DATABASE),
        run_check(request, CHECK_REDIS),
    )
    return [r for r in results if r is not None]


def steps_payload(registry, pending_ids: set[str], translate=None) -> list[dict]:
    """Shape the registered steps for the wizard, resolving their catalog keys.

    Steps are contributed by arbitrary modules, so their titles arrive as
    backend data and cannot go through ``useT()`` in the page. Resolved here
    instead, with the same fallback rule ``MenuRegistry`` uses: an unresolved
    key keeps the English literal, because rendering ``users.administrator`` in
    the UI would be worse than the text it replaced.
    """

    def render(key: str, fallback: str) -> str:
        if not key or translate is None:
            return fallback
        translated = translate(key)
        return fallback if translated == key else translated

    return [
        {
            "id": step.id,
            "title": render(step.title_key, step.title),
            "description": render(step.description_key, step.description),
            "complete": step.id not in pending_ids,
        }
        for step in registry.all_steps
    ]

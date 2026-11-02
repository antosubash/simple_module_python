"""What the setup wizard displays.

Split from ``routes`` so that module holds the routes and the gating that
guards them, while this one holds the read-only shaping of what the page
renders. They change for different reasons: a new dependency to probe touches
this file, a new security condition touches that one.
"""

from __future__ import annotations

import asyncio

from fastapi import Request

from simple_module_hosting._db_health import CHECK_DATABASE

# A health-check *name*, not an import: the check exists only when the
# background_tasks module registered it, and is skipped otherwise.
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


def _resolver(translate):
    """``(key, fallback) -> str`` with the ``MenuRegistry`` fallback rule.

    An unresolved key keeps the English literal, because rendering
    ``users.setup.administrator.title`` in the UI would be worse than the text
    it replaced.
    """

    def render(key: str, fallback: str) -> str:
        if not key or translate is None:
            return fallback
        translated = translate(key)
        return fallback if translated == key else translated

    return render


def _action_payload(action, render) -> dict:
    return {
        "submitLabel": render(action.submit_label_key, action.submit_label),
        "fields": [
            {
                "name": f.name,
                "label": render(f.label_key, f.label),
                "type": f.type,
                "required": f.required,
                "autocomplete": f.autocomplete,
                "minLength": f.min_length,
            }
            for f in action.fields
        ],
    }


def steps_payload(registry, pending_ids: set[str], translate=None) -> list[dict]:
    """Shape the registered steps for the wizard, resolving their catalog keys.

    Steps are contributed by arbitrary modules, so their titles arrive as
    backend data and cannot go through ``useT()`` in the page. Resolved here
    instead.

    A step's form is sent only while that step is pending: the action route
    refuses a completed step anyway, and offering the form would only invite
    a request that is bound to fail.
    """
    render = _resolver(translate)
    out: list[dict] = []
    for step in registry.all_steps:
        pending = step.id in pending_ids
        out.append(
            {
                "id": step.id,
                "title": render(step.title_key, step.title),
                "description": render(step.description_key, step.description),
                "complete": not pending,
                "action": _action_payload(step.action, render) if pending and step.action else None,
            }
        )
    return out

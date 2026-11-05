"""Inertia view endpoints for the BackgroundTasks admin UI."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from simple_module_db.pagination import PageParams
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.pagination import lenient_page_params
from simple_module_hosting.permissions import RequiresPermission
from simple_module_inertia import InertiaResponse, defer

from background_tasks.celery_app import describe_routes
from background_tasks.constants import (
    PERM_VIEW,
    PLATFORM_TENANT_FILTER,
    TaskStatus,
)
from background_tasks.deps import get_background_task_service
from background_tasks.service import BackgroundTaskService
from background_tasks.worker_inspector import redact_broker_url
from background_tasks.workers_state import poll_workers

router = APIRouter(dependencies=[Depends(RequiresPermission(PERM_VIEW))])

PER_PAGE = 20

# Window the "Succeeded 24h" tile counts over.
SUCCESS_WINDOW_HOURS = 24

# Deferred group for props that wait on the broker.
_WORKERS_GROUP = "workers"


async def _worker_presence(request: Request) -> dict[str, object]:
    """Whether anything is actually able to run a task right now.

    An executions table with no rows has two very different causes: nothing has
    been enqueued yet, or a worker was never started and the queue is piling up
    unattended. The empty state cannot tell an operator which without asking
    the broker.

    Polling costs one inspect timeout (~1s), so this is called only when the
    unfiltered list is genuinely empty — the one moment the answer changes what
    the screen should say — and as a deferred prop: the page paints at once
    and the empty state says it is checking until the answer lands.
    """
    snapshot = await poll_workers(request)
    return {
        "broker_reachable": snapshot.broker_reachable,
        "worker_count": sum(1 for w in snapshot.workers if w.online),
    }


async def _snapshot_json(request: Request) -> dict[str, object]:
    """The Workers page's fleet snapshot, loaded as a deferred prop."""
    return (await poll_workers(request)).model_dump(mode="json")


@router.get("/", response_model=None)
async def index(
    inertia: InertiaDep,
    request: Request,
    status: TaskStatus | None = Query(default=None),
    task_name: str = Query(default="", alias="q"),
    queue: str = Query(default=""),
    tenant_id: str = Query(default="", alias="tenant"),
    params: PageParams = Depends(lenient_page_params(PER_PAGE)),
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> InertiaResponse:
    response = await service.list(
        status=status,
        task_name=task_name or None,
        queue=queue or None,
        tenant_id=tenant_id or None,
        page=params.page,
        per_page=PER_PAGE,
    )
    # A filtered-empty list says nothing about the fleet, so don't pay to poll
    # it: the screen already knows to blame the filter.
    unfiltered_and_empty = (
        response.total == 0 and not task_name and not queue and not tenant_id and status is None
    )

    # `total` is the filtered count; the page must tell "the filters hide rows"
    # from "nothing exists at all".
    has_executions = response.total > 0
    if not has_executions and not unfiltered_and_empty:
        has_executions = (await service.list(page=1, per_page=1)).total > 0

    async def strip_data() -> tuple[dict[str, int], list[str]]:
        """Everything above the table. Serial: one session, one connection."""
        counts = await service.status_counts(
            task_name=task_name or None, queue=queue or None, tenant_id=tenant_id or None
        )
        # The strip's third tile is a windowed throughput reading rather than a
        # status total, so it needs its own count — see `success_count_since`.
        counts["success_24h"] = await service.success_count_since(
            hours=SUCCESS_WINDOW_HOURS,
            task_name=task_name or None,
            queue=queue or None,
            tenant_id=tenant_id or None,
        )
        # Deliberately unfiltered: the dropdown is how an operator leaves the
        # queue they are in, so it keeps offering the ones they are not in.
        return counts, await service.queues()

    counts, queues = await strip_data()
    return await inertia.render(
        "BackgroundTasks/Index",
        {
            "executions": [i.model_dump(mode="json") for i in response.items],
            "status_counts": {
                **{s.value: counts.get(s.value, 0) for s in TaskStatus},
                "success_24h": counts["success_24h"],
            },
            "queues": queues,
            "tenant_ids": await service.tenant_ids(),
            "platform_tenant_value": PLATFORM_TENANT_FILTER,
            # Deferred: the broker poll waits out a ~1s inspect timeout, which
            # would otherwise hold back the whole page on a fresh install.
            "worker_presence": (
                defer(lambda: _worker_presence(request), group=_WORKERS_GROUP)
                if unfiltered_and_empty
                else None
            ),
            "has_executions": has_executions,
            "pagination": {
                "page": response.page,
                "per_page": response.per_page,
                "total": response.total,
            },
            "filters": {
                "status": status.value if status else "",
                "task_name": task_name,
                "queue": queue,
                "tenant": tenant_id,
            },
        },
    )


@router.get("/workers", response_model=None)
async def workers(
    inertia: InertiaDep,
    request: Request,
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> InertiaResponse:
    settings = request.app.state.background_tasks.settings
    # The start command the empty state offers has to name the queues this
    # install actually uses, or it starts a worker that consumes nothing. The
    # default queue leads because it is the one that always exists, even before
    # a single task has run.
    routes = describe_routes(settings)
    used_queues = await service.queues()
    queues = [settings.task_default_queue]
    for q in [*(r["queue"] for r in routes), *used_queues]:
        if q and q not in queues:
            queues.append(q)
    return await inertia.render(
        "BackgroundTasks/Workers",
        {
            # Deferred for the same ~1s inspect timeout: the routes and the
            # start command render at once, the fleet fills in behind a skeleton.
            "snapshot": defer(lambda: _snapshot_json(request), group=_WORKERS_GROUP),
            "broker_url_redacted": redact_broker_url(settings.broker_url),
            "queues": queues,
            "routes": routes,
        },
    )


@router.get("/{execution_id}", response_model=None)
async def detail(
    execution_id: str,
    inertia: InertiaDep,
    request: Request,
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> InertiaResponse:
    try:
        eid = uuid.UUID(execution_id)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc
    row = await service.get(eid)
    if row is None:
        raise HTTPException(status_code=404)
    return await inertia.render(
        "BackgroundTasks/Detail",
        {
            "execution": row.model_dump(mode="json"),
            # The subline reads "attempt {n} of {max}"; without the ceiling the
            # attempt count cannot say whether another one is coming.
            "max_retries": request.app.state.background_tasks.settings.max_retries,
        },
    )

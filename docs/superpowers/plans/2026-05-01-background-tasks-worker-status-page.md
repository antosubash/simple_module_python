# Background Tasks Worker Status Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `/admin/background-tasks/workers` sub-page to the `background_tasks` module that surfaces Celery worker presence (hostname, queues, active task count, pool size, total processed) via `celery.control.inspect()`, with a manual Refresh button and no auto-polling.

**Architecture:** A new `WorkerInspector` class wraps Celery's `control.inspect()` API and produces a typed `WorkerSnapshot`. Two new endpoints (Inertia view + JSON) call it via `asyncio.to_thread` so the broker round-trip never blocks the event loop. A new `Workers.tsx` page renders the snapshot from initial Inertia props and updates it via a Refresh button that hits the JSON endpoint with `fetch`. The existing Index page gets a header link.

**Tech Stack:** Python 3.12 + FastAPI + Celery 5 + Inertia.js + React 18 + Tailwind 4 + SQLModel (DTOs only here).

**Spec:** [docs/superpowers/specs/2026-05-01-background-tasks-worker-status-page-design.md](../specs/2026-05-01-background-tasks-worker-status-page-design.md)

**Routing constants (already defined in `background_tasks/constants.py`):**
- `VIEW_PREFIX = "/admin/background-tasks"` → page lives at `/admin/background-tasks/workers`.
- `API_PREFIX = "/api/background_tasks"` and `ADMIN_ROUTER_PREFIX = "/admin"` → JSON endpoint lives at `/api/background_tasks/admin/workers`.
- Existing frontend mirror: `pages/constants.ts` exports `VIEW_BASE = "/admin/background-tasks"` and `API_BASE = "/api/background_tasks/admin"`.

**Files in scope:**
- Create: `modules/background_tasks/background_tasks/worker_inspector.py`
- Create: `modules/background_tasks/background_tasks/pages/Workers.tsx`
- Create: `modules/background_tasks/tests/test_worker_inspector.py`
- Create: `modules/background_tasks/tests/test_workers_endpoints.py`
- Modify: `modules/background_tasks/background_tasks/contracts/schemas.py` (append `WorkerInfo`, `WorkerSnapshot`)
- Modify: `modules/background_tasks/background_tasks/endpoints/api_admin.py` (add `GET /workers`)
- Modify: `modules/background_tasks/background_tasks/endpoints/views.py` (add `GET /workers`)
- Modify: `modules/background_tasks/background_tasks/pages/Index.tsx` (add header link to Workers)

`make gen-pages` regenerates `host/client_app/modules.{manifest.json,generated.ts,generated.css}`. Don't hand-edit those.

---

## Task 1: Add `WorkerInfo` and `WorkerSnapshot` DTOs

**Files:**
- Modify: `modules/background_tasks/background_tasks/contracts/schemas.py`

These DTOs are the contract between the inspector, the endpoints, and the page. Defining them first means later tasks can import them.

- [ ] **Step 1: Add DTOs to schemas.py**

Append to `modules/background_tasks/background_tasks/contracts/schemas.py` (after the existing `TaskExecutionListResponse`):

```python
class WorkerInfo(SQLModel):
    """One Celery worker as reported by ``celery.control.inspect()``."""

    hostname: str
    online: bool
    queues: list[str] = []
    active_task_count: int = 0
    pool_size: int | None = None
    total_processed: int | None = None
    software: str | None = None


class WorkerSnapshot(SQLModel):
    """Point-in-time picture of every worker known to the broker."""

    broker_reachable: bool
    polled_at: datetime
    workers: list[WorkerInfo] = []
    error: str | None = None
```

`datetime` is already imported at the top of the file. No other imports needed.

- [ ] **Step 2: Run linters to confirm the file still parses**

Run: `uv run ruff check modules/background_tasks/background_tasks/contracts/schemas.py`
Expected: PASS (no errors).

- [ ] **Step 3: Commit**

```bash
git add modules/background_tasks/background_tasks/contracts/schemas.py
git commit -m "feat(background_tasks): add WorkerInfo and WorkerSnapshot DTOs"
```

---

## Task 2: Failing test — `WorkerInspector` returns broker-unreachable on connection failure

**Files:**
- Create: `modules/background_tasks/tests/test_worker_inspector.py`

We start with the failure-mode test because it pins down the most important behavior: a dead broker must NOT raise — it must produce a snapshot the page can render.

- [ ] **Step 1: Create the test file with the broker-down test**

Write `modules/background_tasks/tests/test_worker_inspector.py`:

```python
"""Unit tests for WorkerInspector — wraps celery.control.inspect()."""

from __future__ import annotations

from unittest.mock import MagicMock

from celery import Celery


def _make_celery_with_dead_broker() -> Celery:
    """Build a Celery app pointed at an unreachable broker.

    Port 1 is reserved/refused, so any connection attempt fails fast.
    """
    app = Celery("test", broker="redis://127.0.0.1:1/0", backend="redis://127.0.0.1:1/1")
    app.conf.broker_connection_retry_on_startup = False
    return app


def test_dead_broker_returns_unreachable_snapshot():
    from background_tasks.worker_inspector import WorkerInspector

    inspector = WorkerInspector(_make_celery_with_dead_broker(), timeout=0.2)
    snapshot = inspector.snapshot()

    assert snapshot.broker_reachable is False
    assert snapshot.workers == []
    assert snapshot.error is not None
    assert snapshot.polled_at is not None


def test_inspect_payloads_are_merged_into_worker_info():
    from background_tasks.worker_inspector import WorkerInspector

    celery = MagicMock(spec=Celery)
    # Probe call: ensure_connection succeeds (broker reachable).
    celery.connection.return_value.ensure_connection.return_value = None

    inspect = celery.control.inspect.return_value
    inspect.ping.return_value = {"celery@host-a": {"ok": "pong"}}
    inspect.stats.return_value = {
        "celery@host-a": {
            "pool": {"max-concurrency": 4, "processes": [1, 2, 3, 4]},
            "total": {"demo.task": 17},
            "broker": {"transport": "redis"},
            "sw_ident": "py-celery",
            "sw_ver": "5.3.6",
        },
    }
    inspect.active_queues.return_value = {
        "celery@host-a": [{"name": "default"}, {"name": "high"}],
    }
    inspect.active.return_value = {
        "celery@host-a": [{"id": "task-1"}, {"id": "task-2"}],
    }

    snapshot = WorkerInspector(celery, timeout=0.1).snapshot()

    assert snapshot.broker_reachable is True
    assert snapshot.error is None
    assert len(snapshot.workers) == 1
    w = snapshot.workers[0]
    assert w.hostname == "celery@host-a"
    assert w.online is True
    assert w.queues == ["default", "high"]
    assert w.active_task_count == 2
    assert w.pool_size == 4
    assert w.total_processed == 17
    assert w.software == "py-celery:5.3.6"


def test_worker_in_stats_but_not_ping_is_offline():
    from background_tasks.worker_inspector import WorkerInspector

    celery = MagicMock(spec=Celery)
    celery.connection.return_value.ensure_connection.return_value = None
    inspect = celery.control.inspect.return_value
    inspect.ping.return_value = {}  # no replies
    inspect.stats.return_value = {"celery@host-b": {"pool": {"max-concurrency": 2}}}
    inspect.active_queues.return_value = {}
    inspect.active.return_value = {}

    snapshot = WorkerInspector(celery, timeout=0.1).snapshot()

    assert snapshot.broker_reachable is True
    assert len(snapshot.workers) == 1
    assert snapshot.workers[0].hostname == "celery@host-b"
    assert snapshot.workers[0].online is False
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest modules/background_tasks/tests/test_worker_inspector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'background_tasks.worker_inspector'`.

- [ ] **Step 3: Commit (red)**

```bash
git add modules/background_tasks/tests/test_worker_inspector.py
git commit -m "test(background_tasks): add WorkerInspector tests (failing)"
```

---

## Task 3: Implement `WorkerInspector`

**Files:**
- Create: `modules/background_tasks/background_tasks/worker_inspector.py`

- [ ] **Step 1: Write the implementation**

Write `modules/background_tasks/background_tasks/worker_inspector.py`:

```python
"""Read-only adapter around ``celery.control.inspect()``.

Produces a :class:`WorkerSnapshot` for the admin Workers page. All broker
errors are caught and surfaced through ``snapshot.broker_reachable`` /
``snapshot.error`` so the page can render a clear operator-facing state
instead of the endpoint returning a 5xx.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from kombu.exceptions import OperationalError

from background_tasks.contracts.schemas import WorkerInfo, WorkerSnapshot

if TYPE_CHECKING:
    from celery import Celery

logger = logging.getLogger(__name__)


class WorkerInspector:
    """Synchronous adapter; call from async code via ``asyncio.to_thread``."""

    def __init__(self, celery: Celery, *, timeout: float = 1.0) -> None:
        self.celery = celery
        self.timeout = timeout

    def snapshot(self) -> WorkerSnapshot:
        polled_at = datetime.now(UTC)

        # Probe the broker first so we can distinguish "broker down" from
        # "broker up but no workers replied". Without this, both look like
        # ``inspect.*() == None``.
        try:
            with self.celery.connection() as conn:
                conn.ensure_connection(max_retries=1, timeout=self.timeout)
        except (OperationalError, ConnectionError, OSError) as exc:
            logger.info("Broker unreachable: %s", exc)
            return WorkerSnapshot(
                broker_reachable=False,
                polled_at=polled_at,
                workers=[],
                error=str(exc),
            )

        inspect = self.celery.control.inspect(timeout=self.timeout)
        try:
            ping = inspect.ping() or {}
            stats = inspect.stats() or {}
            queues = inspect.active_queues() or {}
            active = inspect.active() or {}
        except (OperationalError, ConnectionError, OSError) as exc:
            logger.info("inspect() failed mid-call: %s", exc)
            return WorkerSnapshot(
                broker_reachable=False,
                polled_at=polled_at,
                workers=[],
                error=str(exc),
            )

        hostnames = sorted(set(ping) | set(stats) | set(queues) | set(active))
        workers = [
            _build_worker_info(
                hostname=h,
                pinged=h in ping,
                stats=stats.get(h) or {},
                queues=queues.get(h) or [],
                active=active.get(h) or [],
            )
            for h in hostnames
        ]
        return WorkerSnapshot(
            broker_reachable=True,
            polled_at=polled_at,
            workers=workers,
            error=None,
        )


def _build_worker_info(
    *,
    hostname: str,
    pinged: bool,
    stats: dict[str, Any],
    queues: list[dict[str, Any]],
    active: list[dict[str, Any]],
) -> WorkerInfo:
    pool = stats.get("pool") or {}
    pool_size = pool.get("max-concurrency")
    if pool_size is None and isinstance(pool.get("processes"), list):
        pool_size = len(pool["processes"])

    total = stats.get("total")
    total_processed: int | None = None
    if isinstance(total, dict):
        total_processed = sum(int(v) for v in total.values() if isinstance(v, int | float))
    elif isinstance(total, int):
        total_processed = total

    sw_ident = stats.get("sw_ident")
    sw_ver = stats.get("sw_ver")
    software = f"{sw_ident}:{sw_ver}" if sw_ident and sw_ver else (sw_ident or sw_ver)

    return WorkerInfo(
        hostname=hostname,
        online=pinged,
        queues=[q.get("name", "") for q in queues if q.get("name")],
        active_task_count=len(active),
        pool_size=pool_size,
        total_processed=total_processed,
        software=software,
    )
```

- [ ] **Step 2: Run the tests to confirm they pass**

Run: `uv run pytest modules/background_tasks/tests/test_worker_inspector.py -v`
Expected: PASS — 3 tests pass.

- [ ] **Step 3: Run the linters on the new file**

Run: `uv run ruff check modules/background_tasks/background_tasks/worker_inspector.py && uv run ty check modules/background_tasks/background_tasks/worker_inspector.py`
Expected: PASS.

- [ ] **Step 4: Commit (green)**

```bash
git add modules/background_tasks/background_tasks/worker_inspector.py
git commit -m "feat(background_tasks): WorkerInspector wraps celery.control.inspect"
```

---

## Task 4: Failing test — JSON `GET /api/background_tasks/admin/workers`

**Files:**
- Create: `modules/background_tasks/tests/test_workers_endpoints.py`

Mirrors the structure of `test_admin_api.py`. We monkeypatch `WorkerInspector.snapshot` to a fixed value so the test is hermetic — no real broker required.

- [ ] **Step 1: Write the failing test**

Write `modules/background_tasks/tests/test_workers_endpoints.py`:

```python
"""End-to-end tests for the Workers endpoints (Inertia view + JSON admin)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest

from background_tasks.contracts.schemas import WorkerInfo, WorkerSnapshot

JSON_BASE = "/api/background_tasks/admin"
VIEW_BASE = "/admin/background-tasks"


@pytest.fixture(autouse=True)
async def _stub_celery(app) -> None:
    """Replace the live Celery instance with a MagicMock for these tests."""
    app.state.background_tasks.celery = MagicMock(name="Celery")


@pytest.fixture
def fake_snapshot() -> WorkerSnapshot:
    return WorkerSnapshot(
        broker_reachable=True,
        polled_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        workers=[
            WorkerInfo(
                hostname="celery@host-a",
                online=True,
                queues=["default"],
                active_task_count=1,
                pool_size=4,
                total_processed=42,
                software="py-celery:5.3.6",
            ),
        ],
        error=None,
    )


class TestWorkersJsonEndpoint:
    async def test_unauthenticated_request_is_rejected(self, client: httpx.AsyncClient):
        resp = await client.get(f"{JSON_BASE}/workers", follow_redirects=False)
        assert resp.status_code in {302, 401, 403}

    async def test_returns_snapshot_payload(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
        fake_snapshot: WorkerSnapshot,
    ):
        from background_tasks import worker_inspector as wi

        monkeypatch.setattr(
            wi.WorkerInspector, "snapshot", lambda self: fake_snapshot
        )

        resp = await authenticated_client.get(f"{JSON_BASE}/workers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["broker_reachable"] is True
        assert len(body["workers"]) == 1
        assert body["workers"][0]["hostname"] == "celery@host-a"
        assert body["workers"][0]["pool_size"] == 4

    async def test_unreachable_broker_is_200_with_error_field(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
    ):
        from background_tasks import worker_inspector as wi

        unreachable = WorkerSnapshot(
            broker_reachable=False,
            polled_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            workers=[],
            error="Connection refused",
        )
        monkeypatch.setattr(wi.WorkerInspector, "snapshot", lambda self: unreachable)

        resp = await authenticated_client.get(f"{JSON_BASE}/workers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["broker_reachable"] is False
        assert body["error"] == "Connection refused"
        assert body["workers"] == []


class TestWorkersInertiaView:
    async def test_renders_page_with_snapshot_prop(
        self,
        monkeypatch,
        authenticated_client: httpx.AsyncClient,
        fake_snapshot: WorkerSnapshot,
    ):
        from background_tasks import worker_inspector as wi

        monkeypatch.setattr(wi.WorkerInspector, "snapshot", lambda self: fake_snapshot)

        # Inertia returns JSON when X-Inertia is present.
        resp = await authenticated_client.get(
            f"{VIEW_BASE}/workers",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["component"] == "BackgroundTasks/Workers"
        snapshot = body["props"]["snapshot"]
        assert snapshot["broker_reachable"] is True
        assert snapshot["workers"][0]["hostname"] == "celery@host-a"
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest modules/background_tasks/tests/test_workers_endpoints.py -v`
Expected: FAIL — the JSON tests get 404 (route not registered) and the Inertia test gets 404 too.

- [ ] **Step 3: Commit (red)**

```bash
git add modules/background_tasks/tests/test_workers_endpoints.py
git commit -m "test(background_tasks): add Workers endpoints tests (failing)"
```

---

## Task 5: Implement `GET /workers` JSON endpoint

**Files:**
- Modify: `modules/background_tasks/background_tasks/endpoints/api_admin.py`

- [ ] **Step 1: Add the workers endpoint**

Apply this edit to `modules/background_tasks/background_tasks/endpoints/api_admin.py`. Replace the imports and add the new endpoint. Updated full file:

```python
"""Admin REST endpoints for BackgroundTasks."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from simple_module_hosting.permissions import RequiresPermission

from background_tasks.constants import (
    ADMIN_ROUTER_PREFIX,
    MODULE_NAME,
    PERM_MANAGE,
    PERM_VIEW,
    TaskStatus,
)
from background_tasks.contracts.schemas import (
    TaskExecutionDetail,
    TaskExecutionListResponse,
    WorkerSnapshot,
)
from background_tasks.deps import get_background_task_service
from background_tasks.service import BackgroundTaskService
from background_tasks.worker_inspector import WorkerInspector

router = APIRouter(
    prefix=ADMIN_ROUTER_PREFIX,
    dependencies=[Depends(RequiresPermission(PERM_VIEW))],
    tags=[f"{MODULE_NAME}-admin"],
)


@router.get("/executions", response_model=TaskExecutionListResponse)
async def list_executions(
    status: TaskStatus | None = Query(default=None),
    task_name: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> TaskExecutionListResponse:
    return await service.list(status=status, task_name=task_name, page=page, per_page=per_page)


@router.get("/executions/{execution_id}", response_model=TaskExecutionDetail)
async def get_execution(
    execution_id: uuid.UUID,
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> TaskExecutionDetail:
    detail = await service.get(execution_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Task execution not found")
    return detail


@router.post(
    "/executions/{execution_id}/retry",
    response_model=TaskExecutionDetail,
    dependencies=[Depends(RequiresPermission(PERM_MANAGE))],
)
async def retry_execution(
    execution_id: uuid.UUID,
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> TaskExecutionDetail:
    return await service.retry(execution_id)


@router.get("/workers", response_model=WorkerSnapshot)
async def get_workers(request: Request) -> WorkerSnapshot:
    """Live snapshot of every Celery worker reachable via the broker."""
    celery = request.app.state.background_tasks.celery
    inspector = WorkerInspector(celery)
    return await asyncio.to_thread(inspector.snapshot)
```

- [ ] **Step 2: Run the JSON-endpoint tests**

Run: `uv run pytest modules/background_tasks/tests/test_workers_endpoints.py::TestWorkersJsonEndpoint -v`
Expected: PASS — 3 tests pass.

The Inertia view test still fails (route not added yet); that's expected.

- [ ] **Step 3: Commit**

```bash
git add modules/background_tasks/background_tasks/endpoints/api_admin.py
git commit -m "feat(background_tasks): add GET /admin/workers JSON endpoint"
```

---

## Task 6: Implement `GET /workers` Inertia view

**Files:**
- Modify: `modules/background_tasks/background_tasks/endpoints/views.py`

- [ ] **Step 1: Add the Inertia workers route**

Apply this edit to `modules/background_tasks/background_tasks/endpoints/views.py`. Updated full file:

```python
"""Inertia view endpoints for the BackgroundTasks admin UI."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from background_tasks.constants import (
    PERM_VIEW,
    TaskStatus,
)
from background_tasks.deps import get_background_task_service
from background_tasks.service import BackgroundTaskService
from background_tasks.worker_inspector import WorkerInspector

router = APIRouter(dependencies=[Depends(RequiresPermission(PERM_VIEW))])

PER_PAGE = 20


@router.get("/", response_model=None)
async def index(
    inertia: InertiaDep,
    status: TaskStatus | None = Query(default=None),
    task_name: str = Query(default="", alias="q"),
    page: int = Query(default=1, ge=1),
    service: BackgroundTaskService = Depends(get_background_task_service),
) -> InertiaResponse:
    response = await service.list(
        status=status,
        task_name=task_name or None,
        page=page,
        per_page=PER_PAGE,
    )
    return await inertia.render(
        "BackgroundTasks/Index",
        {
            "executions": [i.model_dump(mode="json") for i in response.items],
            "pagination": {
                "page": response.page,
                "per_page": response.per_page,
                "total": response.total,
            },
            "filters": {
                "status": status.value if status else "",
                "task_name": task_name,
            },
        },
    )


@router.get("/workers", response_model=None)
async def workers(inertia: InertiaDep, request: Request) -> InertiaResponse:
    celery = request.app.state.background_tasks.celery
    snapshot = await asyncio.to_thread(WorkerInspector(celery).snapshot)
    return await inertia.render(
        "BackgroundTasks/Workers",
        {"snapshot": snapshot.model_dump(mode="json")},
    )


@router.get("/{execution_id}", response_model=None)
async def detail(
    execution_id: str,
    inertia: InertiaDep,
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
        {"execution": row.model_dump(mode="json")},
    )
```

**Note on route ordering:** `/workers` must be declared *before* `/{execution_id}` because FastAPI matches routes in registration order. If `/{execution_id}` came first, `/workers` would be captured as a UUID, hit the `ValueError` branch, and return 404. The placement above is correct — keep it.

- [ ] **Step 2: Run all the workers endpoint tests**

Run: `uv run pytest modules/background_tasks/tests/test_workers_endpoints.py -v`
Expected: PASS — all 4 tests pass.

- [ ] **Step 3: Run the existing background_tasks suite to confirm no regression**

Run: `uv run pytest modules/background_tasks/tests/ -v`
Expected: PASS — every test passes (existing + new).

- [ ] **Step 4: Commit**

```bash
git add modules/background_tasks/background_tasks/endpoints/views.py
git commit -m "feat(background_tasks): add /workers Inertia view"
```

---

## Task 7: Add the `Workers.tsx` page

**Files:**
- Create: `modules/background_tasks/background_tasks/pages/Workers.tsx`

This is the operator-facing UI. Plain `fetch` for the Refresh button (per the spec — it's a read-only GET, no Inertia partial-reload needed).

- [ ] **Step 1: Write the page**

Write `modules/background_tasks/background_tasks/pages/Workers.tsx`:

```tsx
import { Link, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { ArrowLeft, RefreshCw, ServerCrash, ServerOff } from 'lucide-react';
import { useState } from 'react';
import { API_BASE, VIEW_BASE } from './constants';

interface WorkerInfo {
  hostname: string;
  online: boolean;
  queues: string[];
  active_task_count: number;
  pool_size: number | null;
  total_processed: number | null;
  software: string | null;
}

interface WorkerSnapshot {
  broker_reachable: boolean;
  polled_at: string;
  workers: WorkerInfo[];
  error: string | null;
}

interface Props {
  snapshot: WorkerSnapshot;
}

function formatPolledAt(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString();
}

function WorkerCard({ worker }: { worker: WorkerInfo }) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span
            className={`mt-1.5 size-2.5 rounded-full ${
              worker.online ? 'bg-green-500' : 'bg-muted-foreground'
            }`}
            aria-label={worker.online ? 'online' : 'offline'}
          />
          <div>
            <h3 className="font-medium">{worker.hostname}</h3>
            {worker.software && (
              <p className="text-xs text-muted-foreground">{worker.software}</p>
            )}
          </div>
        </div>
        <Badge variant={worker.online ? 'secondary' : 'outline'}>
          {worker.online ? 'Online' : 'Offline'}
        </Badge>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">Active</dt>
          <dd className="font-medium">{worker.active_task_count}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Pool</dt>
          <dd className="font-medium">{worker.pool_size ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Processed</dt>
          <dd className="font-medium">{worker.total_processed ?? '—'}</dd>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <dt className="text-muted-foreground">Queues</dt>
          <dd className="flex flex-wrap gap-1">
            {worker.queues.length === 0 ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              worker.queues.map((q) => (
                <Badge key={q} variant="outline" className="font-normal">
                  {q}
                </Badge>
              ))
            )}
          </dd>
        </div>
      </dl>
    </Card>
  );
}

function Workers() {
  const { snapshot: initial } = usePage<{ props: Props }>().props as unknown as Props;
  const [snapshot, setSnapshot] = useState<WorkerSnapshot>(initial);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/workers`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        setSnapshot((await res.json()) as WorkerSnapshot);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageShell
      title="Workers"
      description="Celery workers connected to the broker."
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <Button variant="outline" size="sm" asChild>
          <Link href={VIEW_BASE}>
            <ArrowLeft className="mr-2 size-4" />
            Back to executions
          </Link>
        </Button>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            Last updated {formatPolledAt(snapshot.polled_at)}
          </span>
          <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
            <RefreshCw className={`mr-2 size-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {!snapshot.broker_reachable ? (
        <Card className="p-6">
          <div className="flex items-start gap-3">
            <ServerCrash className="size-5 text-destructive" />
            <div>
              <h3 className="font-medium">Broker unreachable</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                {snapshot.error ?? 'No error message reported.'}
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                Check the <code>SM_BG_TASKS_BROKER_URL</code> setting and confirm the broker
                process is running.
              </p>
            </div>
          </div>
        </Card>
      ) : snapshot.workers.length === 0 ? (
        <Card className="p-6">
          <div className="flex items-start gap-3">
            <ServerOff className="size-5 text-muted-foreground" />
            <div>
              <h3 className="font-medium">No workers connected</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                The broker is reachable but no Celery workers are responding. Start one with{' '}
                <code>uv run python scripts/run_worker.py</code>.
              </p>
            </div>
          </div>
        </Card>
      ) : (
        <div className="grid gap-3">
          {snapshot.workers.map((w) => (
            <WorkerCard key={w.hostname} worker={w} />
          ))}
        </div>
      )}
    </PageShell>
  );
}

Workers.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Workers;
```

- [ ] **Step 2: Regenerate the page manifest**

Run: `make gen-pages`
Expected: writes/updates `host/client_app/modules.{manifest.json,generated.ts,generated.css}`. The new `Workers` page should appear under the `BackgroundTasks/` namespace.

- [ ] **Step 3: Confirm Biome accepts the new file**

Run: `npx biome check modules/background_tasks/background_tasks/pages/Workers.tsx`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add modules/background_tasks/background_tasks/pages/Workers.tsx host/client_app/modules.manifest.json host/client_app/modules.generated.ts host/client_app/modules.generated.css
git commit -m "feat(background_tasks): add Workers admin page"
```

---

## Task 8: Add header link from Index page to Workers page

**Files:**
- Modify: `modules/background_tasks/background_tasks/pages/Index.tsx`

The Index page has no sidebar entry pointing at Workers (per the design — no new sidebar item), so the only discovery path is from the existing list page.

- [ ] **Step 1: Add the link in the toolbar**

Apply this edit to `modules/background_tasks/background_tasks/pages/Index.tsx`. Find the existing toolbar div (the `flex` container with the search input and status select) and add a "Workers" link button to its right, plus the `Link` and `ServerCog` imports. The updated relevant region:

Replace the existing import block top-of-file with:

```tsx
import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Activity, Search, ServerCog } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ExecutionRow, statusLabel } from './components/ExecutionRow';
import { STATUS_ORDER, VIEW_BASE } from './constants';
import { type Execution, retryExecution } from './retry';
```

Replace the existing toolbar `<div className="mb-4 flex flex-col sm:flex-row …">…</div>` block with:

```tsx
      <div className="mb-4 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Search by task name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={statusValue}
            onValueChange={(v) => pushFilters({ status: v, task_name: search }, 1)}
          >
            <SelectTrigger className="w-full sm:w-48">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={STATUS_ALL}>All statuses</SelectItem>
              {STATUS_ORDER.map((s) => (
                <SelectItem key={s} value={s}>
                  {statusLabel(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" asChild>
            <Link href={`${VIEW_BASE}/workers`}>
              <ServerCog className="mr-2 size-4" />
              Workers
            </Link>
          </Button>
        </div>
      </div>
```

The change: wrapped the existing `<Select>` and the new `<Button>`/`<Link>` together in a `flex items-center gap-2` div so they sit side-by-side on the right.

- [ ] **Step 2: Confirm Biome accepts the changes**

Run: `npx biome check modules/background_tasks/background_tasks/pages/Index.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add modules/background_tasks/background_tasks/pages/Index.tsx
git commit -m "feat(background_tasks): link to Workers page from Index toolbar"
```

---

## Task 9: Verify diagnostics and lint suite end-to-end

**Files:** none (verification only).

- [ ] **Step 1: Run module diagnostics**

Run: `make doctor`
Expected: no new errors. Specifically:
- `SM003` (orphan page) should NOT fire — `Workers.tsx` is rendered by `views.py:workers`.
- `SM004` (phantom render) should NOT fire — both render call and page file exist.
- `SM018` should NOT fire — `Workers.tsx` uses plain `fetch`, not Inertia router.
- `SM019` should NOT fire — the module already registers permissions; adding a sub-page doesn't change that.

If any of those fire, re-read the spec's "Diagnostics check" section and reconcile.

- [ ] **Step 2: Run the full lint suite**

Run: `make lint`
Expected: PASS — Ruff format, Ruff lint, ty, Biome, per-workspace tsc, and the 300-line file cap all pass. If the 300-line check flags `Workers.tsx`, split out the `WorkerCard` component into `pages/components/WorkerCard.tsx` (mirroring the existing `ExecutionRow.tsx` split).

- [ ] **Step 3: Run the full Python + JS test suite**

Run: `make test`
Expected: PASS — every existing test plus the new `test_worker_inspector.py` and `test_workers_endpoints.py` pass.

- [ ] **Step 4: Commit any cleanup if a split was needed**

```bash
git add -A
git commit -m "chore(background_tasks): split WorkerCard for file-size budget"
```

(Skip this commit if no split was needed.)

---

## Task 10: Manual smoke test in dev

**Files:** none (manual verification).

- [ ] **Step 1: Start the dev stack**

Run: `make dev`
Wait until the API logs `Application startup complete` and Vite reports `ready in <ms>`.

- [ ] **Step 2: Sign in and exercise three states**

1. **Broker unreachable.** Stop the Redis container (`docker compose stop redis` from the project root, or whatever `make dev` brings up) and visit `http://localhost:8000/admin/background-tasks/workers`. Expected: "Broker unreachable" card with the connection error.
2. **Broker up, no workers.** Start Redis (`docker compose start redis`), do NOT start a worker. Reload the page or click Refresh. Expected: "No workers connected" card.
3. **Worker connected.** In a separate terminal: `uv run python scripts/run_worker.py`. Click Refresh. Expected: one worker card showing the hostname, "Online" badge, the `default` queue badge, pool size, and a `0` active count. Trigger a task (e.g. via `make dev`'s usual flows or `from background_tasks.tasks import demo_echo; demo_echo.delay(...)` from a Python REPL) and click Refresh — `Active` should briefly show `1`.

- [ ] **Step 3: Confirm the link from Index works**

Navigate to `http://localhost:8000/admin/background-tasks` and click the "Workers" button in the toolbar. It should load the Workers page. Click "Back to executions" — it should return to the Index.

- [ ] **Step 4: No commit; just confirm the smoke test passes**

If everything works, the feature is done. If anything failed, file the regression as a follow-up — don't paper over it.

---

## Done

At this point:
- `WorkerInspector` is unit-tested against both healthy and broker-down conditions.
- `GET /api/background_tasks/admin/workers` returns the snapshot as JSON for the Refresh button.
- `GET /admin/background-tasks/workers` renders the `BackgroundTasks/Workers` Inertia page.
- The Workers page handles all three states (broker down / no workers / workers present) and refreshes on demand.
- The Index page has a discoverable link to Workers.
- `make doctor`, `make lint`, and `make test` all pass.

# Background Tasks — Worker Status Page

**Date:** 2026-05-01
**Module:** `background_tasks`
**Status:** design

## Problem

The Background Tasks admin page (`/background-tasks`) shows a list of `TaskExecution` rows, but gives no signal about whether a Celery worker is actually connected and consuming jobs. If the worker process is down or pointed at the wrong broker, the symptom an operator sees today is "tasks stay in `pending` forever" — which is hard to distinguish from "no tasks have been enqueued yet." We need a direct view of worker presence and what each worker is doing.

## Goals

- Surface, in the admin UI, whether at least one worker is connected to the broker.
- For each connected worker, show: hostname, the queues it's consuming, how many tasks it's currently running, pool size, and total tasks processed.
- Distinguish "broker reachable, no workers" from "broker unreachable" so operators know where to look.
- Refresh on demand without auto-polling.

## Non-goals

- No worker control (no remote shutdown, restart, queue-add, rate-limit). Read-only.
- No historical worker uptime / heartbeat graphing — only the current snapshot.
- No new permission. Reuses `background_tasks.view`.
- No sidebar entry. The page is reached via a link from the Index page header.
- No auto-polling. Operator clicks Refresh.

## Architecture

A new sub-page on the existing `background_tasks` module. No DB schema change, no new module, no migration.

```
background_tasks/
├── worker_inspector.py   # NEW — wraps celery.control.inspect()
├── contracts/schemas.py  # MODIFIED — add WorkerInfo, WorkerSnapshot
├── endpoints/
│   ├── api_admin.py      # MODIFIED — add GET /workers
│   └── views.py          # MODIFIED — add GET /workers
├── pages/
│   ├── Index.tsx         # MODIFIED — add header link to Workers page
│   └── Workers.tsx       # NEW
└── module.py             # unchanged
```

`WorkerInspector` is a small standalone class in its own file rather than being added to `BackgroundTaskService`, because its dependencies and failure modes are different: it touches Celery's `control.inspect()` (broker round-trip, can timeout) and never touches the DB. Keeping it separate also keeps `service.py` from drifting toward the 300-line cap.

## Components

### `background_tasks/worker_inspector.py`

```python
class WorkerInspector:
    def __init__(self, celery: Celery, *, timeout: float = 1.0) -> None: ...
    def snapshot(self) -> WorkerSnapshot: ...
```

`snapshot()` is synchronous (Celery's `inspect()` API is sync). It is called from async endpoints via `asyncio.to_thread(...)` so the event loop is not blocked by the broker round-trip.

Implementation:

1. Build `inspect = celery.control.inspect(timeout=self.timeout)`.
2. Call, in order: `ping()`, `stats()`, `active_queues()`, `active()`. Each returns `dict[hostname, payload] | None` (None means "no replies within timeout").
3. If `ping()` is `None` *and* the underlying connection raised — surface as `broker_reachable=False`. We detect this by wrapping the inspect calls in `try/except` for `kombu.exceptions.OperationalError` and `ConnectionError`. Note that `inspect()` returns `None` both when the broker is up but no workers reply, and when the broker is down — so we run a probe `celery.connection().ensure_connection(max_retries=1, timeout=self.timeout)` first to disambiguate, and *that's* what flips `broker_reachable`.
4. Merge per-hostname payloads into `WorkerInfo` rows. A worker that appears in `stats()` but not `ping()` is reported with `online=False` (it was alive recently but isn't responding now).
5. Return a `WorkerSnapshot` with `polled_at = datetime.now(UTC)`.

Errors caught and converted to `WorkerSnapshot(broker_reachable=False, workers=[], error=str(exc))` rather than raising — the page should always render.

### `background_tasks/contracts/schemas.py` (additions)

```python
class WorkerInfo(SQLModel):
    hostname: str
    online: bool
    queues: list[str] = []
    active_task_count: int = 0
    pool_size: int | None = None
    total_processed: int | None = None  # sum across stats()['total']
    software: str | None = None         # e.g. "celery:5.3.6"

class WorkerSnapshot(SQLModel):
    broker_reachable: bool
    polled_at: datetime
    workers: list[WorkerInfo] = []
    error: str | None = None
```

Both are plain SQLModel DTOs (no `table=True`). Same module conventions as the existing `TaskExecutionListItem`.

### `endpoints/api_admin.py` (addition)

```python
@router.get("/workers", response_model=WorkerSnapshot)
async def get_workers(request: Request) -> WorkerSnapshot:
    celery = request.app.state.background_tasks.celery
    inspector = WorkerInspector(celery)
    return await asyncio.to_thread(inspector.snapshot)
```

Uses the router's existing `RequiresPermission(PERM_VIEW)` — no separate permission. Path is `/api/background-tasks/workers` once the admin prefix is applied.

### `endpoints/views.py` (addition)

```python
@router.get("/workers", response_model=None)
async def workers(inertia: InertiaDep, request: Request) -> InertiaResponse:
    celery = request.app.state.background_tasks.celery
    snapshot = await asyncio.to_thread(WorkerInspector(celery).snapshot)
    return await inertia.render(
        "BackgroundTasks/Workers",
        {"snapshot": snapshot.model_dump(mode="json")},
    )
```

Same `RequiresPermission(PERM_VIEW)` (already on the router). Renders the page with an initial snapshot; the Refresh button on the page hits `/api/background-tasks/workers` and replaces the snapshot in component state.

### `pages/Workers.tsx`

Page structure (using the same `PageShell` + `AuthenticatedLayout` pattern as `Index.tsx`):

- Title: "Workers", description: "Celery workers connected to the broker."
- Top-right: Refresh button + "Last updated <relative time>".
- If `snapshot.broker_reachable === false`:
  - Single error card: "Broker unreachable" + the error message + a hint to check the broker URL setting.
- Else if `snapshot.workers.length === 0`:
  - Empty state card: "No workers connected. Start a worker with `uv run python scripts/run_worker.py`."
- Else:
  - One `Card` per worker, with: hostname (heading), green/grey dot for `online`, queue badges, "N active tasks", pool size, total processed, software version.

A "← Back to executions" link in the header. Index page gets a corresponding "Workers →" link (or an icon button) in its header so the page is discoverable without a sidebar entry.

Refresh button click handler:

```ts
async function refresh() {
  setLoading(true);
  try {
    const res = await fetch('/api/background-tasks/workers', { headers: { Accept: 'application/json' } });
    if (res.ok) setSnapshot(await res.json());
  } finally {
    setLoading(false);
  }
}
```

Plain `fetch` is fine here — it's a GET, no CSRF concern (cookie SameSite=Lax handles cross-site protection per CLAUDE.md), and Inertia's `router.get` would force a full page partial-reload which is heavier than we need.

### `pages/Index.tsx` (modification)

Add a small header-row link next to the title — a `Button` with `variant="outline"`, `asChild`, wrapping a Link to `/background-tasks/workers`. Label: "Workers". The page-shell `description` stays the same.

## Data flow

```
Operator opens /background-tasks/workers
  → views.py:workers
  → WorkerInspector.snapshot() in thread
    → celery.connection().ensure_connection(max_retries=1)        # broker reachable?
    → inspect = celery.control.inspect(timeout=1.0)
    → inspect.ping(), .stats(), .active_queues(), .active()       # in worker pool
    → merge → WorkerSnapshot
  → Inertia renders Workers.tsx with snapshot

Operator clicks Refresh
  → fetch GET /api/background-tasks/workers
  → api_admin.py:get_workers
  → same WorkerInspector.snapshot() path
  → setSnapshot(json)
```

## Error handling

All broker-side errors are caught inside `WorkerInspector.snapshot()` and surfaced through `WorkerSnapshot.error` + `broker_reachable=False`. The endpoint never raises 5xx for inspector failures — the page is the right place to surface the operator-facing message.

The two specific exceptions caught:

- `kombu.exceptions.OperationalError` — broker connection refused / DNS / auth.
- `ConnectionError` (and `socket.timeout` on the connection probe) — network-level.

Anything else propagates and becomes a 500, because it represents a real bug rather than an expected operational state.

## Testing

Backend (`modules/background_tasks/tests/test_worker_inspector.py`):

- `WorkerInspector.snapshot()` against a Celery instance configured with a non-existent broker → returns `broker_reachable=False, workers=[]`.
- `WorkerInspector` with `celery.control.inspect` monkeypatched to return canned `ping`/`stats`/`active`/`active_queues` dicts → returns the merged `WorkerSnapshot` with the expected `WorkerInfo` rows.
- A worker present in `stats()` but absent from `ping()` → `WorkerInfo.online == False`.

Endpoint tests (extend `modules/background_tasks/tests/test_endpoints.py` or sibling):

- `GET /background-tasks/workers` (Inertia) returns 200 and the page name `BackgroundTasks/Workers` with a `snapshot` prop. Patch `WorkerInspector.snapshot` to a fixed value.
- `GET /api/background-tasks/workers` returns the same `WorkerSnapshot` shape as JSON.
- Both endpoints require `background_tasks.view` (existing test pattern: hit with a non-permissioned client → 403).

Frontend (`modules/background_tasks/tests/Workers.test.tsx` if a JS test suite exists for the module — check before adding):

- Renders broker-unreachable state when `snapshot.broker_reachable === false`.
- Renders empty state when no workers.
- Renders one card per worker with hostname / queues / counts.
- Refresh button calls `fetch('/api/background-tasks/workers')` and updates state from the response (mock fetch).

E2E is out of scope for this change.

## Diagnostics check

- `SM018` (Inertia `router.{post,…}` to `/api/*`) — N/A; we use plain `fetch`, not Inertia router.
- `SM003`/`SM004` (orphan / phantom Inertia page) — the new `Workers.tsx` is rendered by the new view endpoint. Both must be added together.
- 300-line cap — `Workers.tsx` is expected to land around 120 lines; `worker_inspector.py` around 90. Neither is at risk.

## Build sequence

1. Add `WorkerInfo` / `WorkerSnapshot` to `contracts/schemas.py`.
2. Add `worker_inspector.py` with unit tests (broker-down + monkeypatched-inspect cases).
3. Add `GET /workers` to `api_admin.py` with an endpoint test.
4. Add `GET /workers` to `views.py` with an endpoint test.
5. Add `pages/Workers.tsx`.
6. Modify `pages/Index.tsx` to link to the Workers page.
7. `make gen-pages` to update `host/client_app/modules.{manifest.json,generated.ts,generated.css}`.
8. `make lint` + `make test`.

## Open questions

None.

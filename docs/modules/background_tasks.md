# background_tasks

Celery + Redis task queue with persistent history, an admin UI for monitoring + retrying tasks, and a live worker dashboard. Other modules drop `@celery.task`-decorated functions into their `tasks.py` and they're auto-discovered at boot.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `BackgroundTasks` |
| `route_prefix` | `/api/background_tasks` |
| `view_prefix` | `/admin/background-tasks` |
| `depends_on` | `["Users"]` |

## Writing a task

```python
# modules/orders/orders/tasks.py
from celery import shared_task


@shared_task(name="orders.send_receipt")
def send_receipt(order_id: int) -> None: ...
```

That's it. Celery's `autodiscover_tasks(packages, related_name="tasks")` finds it at worker startup — no extra registration. From request code:

```python
from orders.tasks import send_receipt

send_receipt.delay(order_id=42)
```

Every dispatch / start / completion / failure / retry / revoke is recorded in the `background_tasks_task_execution` table by Celery signal handlers, so you can see history even after the Celery result backend has expired the result.

## Scheduling periodic work (beat)

A module schedules recurring work the same way it registers tasks — by shipping a `tasks.py` — and additionally exporting a module-level `BEAT_SCHEDULE` dict. `build_celery` merges every installed module's `BEAT_SCHEDULE` into the beat schedule at boot (identically in the web and worker processes), so `make beat` runs them alongside the built-ins:

```python
# modules/invoices/invoices/tasks.py
from celery import shared_task
from celery.schedules import crontab


@shared_task(name="invoices.generate_recurring")
def generate_recurring() -> int: ...


# Discovered by build_celery and merged into the beat schedule.
BEAT_SCHEDULE = {
    "invoices-generate-recurring-daily": {
        "task": "invoices.generate_recurring",
        "schedule": crontab(hour=6, minute=0),  # 0 6 * * *
    },
}
```

Entry values are plain Celery [beat entries](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html#entries): `schedule` accepts a number of seconds, a `crontab(...)`, or a `solar(...)`. The two built-in entry names (`background-tasks-sweep-stuck`, `background-tasks-purge-old`) are authoritative — a module reusing one is ignored with a warning.

> **Don't reach for `from celery.signals import on_after_configure`.** It's an *app-instance* signal (not a member of `celery.signals`, so the import raises), and `build_celery` runs `conf.update(...)` — which fires it — *before* `autodiscover_tasks` imports your `tasks.py`, so a handler would miss the window. The declarative `BEAT_SCHEDULE` dict above is the supported mechanism. If you need entries computed at runtime, Celery's `@app.on_after_finalize.connect` + `sender.add_periodic_task(...)` also works.

## Running workers

| Command | Use case |
|---|---|
| `make worker` | Local Celery worker against the configured broker. |
| `make beat` | Local beat scheduler (`sweep_stuck_tasks`, `purge_old_executions`, plus any beat schedules other modules add). |
| `make worker-docker` | Worker + beat services via `docker compose` — matches the prod image. |

Beat persists its schedule (`celery.beat:PersistentScheduler`) so it survives restarts.

## Routes

### Admin API

All require `background_tasks.view`; retry additionally needs `background_tasks.manage`.

| Method + path | Body / response | Notes |
|---|---|---|
| `GET /api/background_tasks/admin/executions` | `?status=&task_name=&page=&per_page=` → `TaskExecutionListResponse` | per_page max 200 |
| `GET /api/background_tasks/admin/executions/{execution_id}` | → `TaskExecutionDetail` | 404 if missing |
| `POST /api/background_tasks/admin/executions/{execution_id}/retry` | → `TaskExecutionDetail` | 409 unless status is `failed` or `stuck` |
| `GET /api/background_tasks/admin/workers` | → `WorkerSnapshot` | live ping; consumed by the `Workers` page |

### View

| Method + path | Inertia component | Permission |
|---|---|---|
| `GET /admin/background-tasks/` | `BackgroundTasks/Index` | `background_tasks.view` |
| `GET /admin/background-tasks/workers` | `BackgroundTasks/Workers` | `background_tasks.view` |
| `GET /admin/background-tasks/{execution_id}` | `BackgroundTasks/Detail` | `background_tasks.view` |

## Public contracts

```python
from background_tasks.contracts.events import TaskFailed, TaskRetried
from background_tasks.contracts.schemas import (
    TaskExecutionListItem,
    TaskExecutionDetail,
    TaskExecutionListResponse,
    WorkerInfo,
    WorkerSnapshot,
)
```

| Class | Purpose |
|---|---|
| `TaskFailed` (event) | Published when a task transitions to `failed`. Fields: `task_execution_id`, `task_name`, `exception_type`. |
| `TaskRetried` (event) | Published when an admin retries via the UI. Fields: `original_id`, `new_id`, `task_name`. |
| `TaskExecutionListItem` | Compact row for the listing table. |
| `TaskExecutionDetail` | Full record incl. `args`, `kwargs`, `result`, `traceback`. |
| `WorkerInfo` / `WorkerSnapshot` | Live worker probe response shape. |

## Models

`TaskExecution` (table `background_tasks_task_execution`)

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK; row stays stable across the task's lifecycle |
| `celery_task_id` | `str(64)` | indexed; updated by signal handlers |
| `task_name` | `str(255)` | indexed |
| `status` | `TaskStatus` | indexed; one of `pending` `running` `success` `failed` `stuck` `revoked` `retrying` |
| `queue` | `str(64)` | default `"default"` |
| `args` / `kwargs` | JSON | |
| `result` | JSON \| `None` | |
| `traceback` | `str \| None` | |
| `exception_type` | `str(255) \| None` | |
| `worker` | `str(255) \| None` | hostname that ran it |
| `retries` | `int` | |
| `retried_from_id` | `UUID \| None` | self-FK; tracks retry chains |
| `queued_at` / `started_at` / `finished_at` / `heartbeat_at` | `datetime` | |
| audit | from `AuditMixin` | |

Composite index on `(status, queued_at)` keeps the listing snappy under load.

## Settings

DB-backed; defaults are in `BackgroundTasksSettings`. Several are marked `requires_restart=True` because Celery reads them at process start.

| Field | Default | Notes |
|---|---|---|
| `broker_url` | `redis://localhost:6379/0` | restart required; rejected as `localhost` in production |
| `result_backend` | `redis://localhost:6379/1` | restart required |
| `task_default_queue` | `"default"` | restart required |
| `task_always_eager` | `False` | runs tasks in-process (test mode) |
| `task_eager_propagates` | `True` | re-raises eager-mode errors |
| `stuck_after_seconds` | `300` | heartbeat-staleness threshold |
| `stuck_sweep_interval_seconds` | `60` | beat cadence for the stuck sweep |
| `purge_interval_seconds` | `86_400` | beat cadence for old-row purge |
| `retention_days` | `14` | how long to keep terminal rows; range 1-3650 |
| `max_retries` | `3` | informational; tasks define their own policies; range 0-100 |

Bootstrap env-var equivalents (`SM_BG_TASKS_*`) only seed pydantic defaults at first boot — once a value lives in the DB, it's authoritative.

## Permissions

| Code | Purpose |
|---|---|
| `background_tasks.view` | list + detail + worker snapshot |
| `background_tasks.manage` | retry failed / stuck tasks |

## Menu

| Label | URL | Icon | Section | Group | Order | Roles |
|---|---|---|---|---|---|---|
| `Background Tasks` | `/admin/background-tasks` | `activity` | `SIDEBAR` | `Administration` | `120` | `["admin"]` |

## Beat schedule (built-in)

| Task | Schedule | What |
|---|---|---|
| `background_tasks.sweep_stuck_tasks` | every `stuck_sweep_interval_seconds` | flips `running` rows with stale heartbeats to `stuck` |
| `background_tasks.purge_old_executions` | every `purge_interval_seconds` | deletes terminal rows older than `retention_days` |

A `background_tasks.demo_echo` task is also registered for smoke tests; not scheduled.

Other modules contribute their own periodic entries via `tasks.BEAT_SCHEDULE` — see [Scheduling periodic work (beat)](#scheduling-periodic-work-beat).

## Events

Published (and consumable from any other module):

- `TaskFailed` — fired from `task_failure` signal when an event bus is bound (web process). Workers don't fire it directly.
- `TaskRetried` — fired from the admin retry path.

## Worker introspection

`WorkerInspector` (`background_tasks/worker_inspector.py`) wraps `celery.control.inspect()`:

| Method | Returns |
|---|---|
| `snapshot()` | `WorkerSnapshot` — one round-trip ping + stats + active queues + active tasks. Sets `broker_reachable=False` and an `error` string if it can't reach the broker. |

It's synchronous; the view route calls it via `asyncio.to_thread`.

## Celery signal hooks

Synchronous handlers in `signals.py`, all bound through Celery's `signals.<name>.connect`, persisting through a separate **sync** SQLAlchemy engine (`sync_db.py`) so they don't have to spin up an event loop:

| Signal | What it writes |
|---|---|
| `before_task_publish` | inserts a `pending` row |
| `task_prerun` | flips to `running`, stamps `started_at` + `heartbeat_at` |
| `task_postrun` | refreshes `heartbeat_at` |
| `task_success` | flips to `success`, stores `result`, sets `finished_at` |
| `task_failure` | flips to `failed`, stores `traceback` + `exception_type`, publishes `TaskFailed` |
| `task_retry` | flips to `retrying`, increments `retries` |
| `task_revoked` | flips to `revoked` |

Production deployments running multiple workers can write concurrently because every update keys off `celery_task_id`.

## Inertia pages

- `BackgroundTasks/Index.tsx` — paginated execution list with status / task-name filters.
- `BackgroundTasks/Detail.tsx` — full execution view with retry button (`background_tasks.manage`).
- `BackgroundTasks/Workers.tsx` — live worker dashboard.
- Components: `ExecutionRow.tsx`, `RetryConfirmDialog.tsx`.

## Locales

Top-level keys in `background_tasks/locales/en.json`: `index`, `filters`, `status` (per-state labels), `table`, `detail`, `retry_dialog`, `toasts`.

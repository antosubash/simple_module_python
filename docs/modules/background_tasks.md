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

## Enqueueing from inside a transaction

`send_receipt.delay(...)` publishes *now*. If the request that called it is still writing the row the task will read, two things go wrong: a fast worker (or eager mode, which runs the task inside the publish) starts before the row is visible, and if the commit then fails the task is queued against a row that never existed. Publish after commit instead:

```python
from background_tasks import enqueue_after_commit


async def place(self, data: OrderCreate) -> OrderOut:
    order = Order(**data.model_dump())
    self.db.add(order)
    await self.db.flush()
    enqueue_after_commit(self.db, send_receipt, order.id)
    return OrderOut.model_validate(order)
```

`enqueue_after_commit(db, task, *args, **kwargs)` sends `task` once `db`'s transaction commits and drops it if the transaction rolls back or the commit fails. It returns the Celery task id the message will carry, reserved up front, so you can store it on your own row in the same transaction.

- `task` is a task (`send_receipt`), a signature for routing options (`send_receipt.s().set(queue="mail", countdown=30)`), or a registered task name (`"orders.send_receipt"`, sent through `celery.current_app`).
- In a request (`get_db`), the publish runs from the session's `on_commit` hook — after the commit, before the response leaves.
- Any other session — a task body's sync session, a CLI script's own `async with session.begin()` — hangs it off SQLAlchemy's `after_commit` event instead, and drops it when the outermost transaction ends without committing. Publishing then blocks the committing thread for the length of one kombu publish.
- The task runs as the tenant bound when you called `enqueue_after_commit`, not whatever is bound at commit time.
- A publish that fails after the commit is logged, not raised: the transaction is already durable.

The admin retry buttons follow the same rule — the new `pending` row commits first, then the task is sent (GH #452). If the send itself then fails, the new row is flipped to `failed` so the retry buttons can pick it up again; a task with no row is neither.

## Long-running tasks: heartbeats and stuck thresholds

The beat sweep flips a `running` row to `stuck` once its `heartbeat_at` is older than the stuck threshold (`stuck_after_seconds`, default 300), which makes it retry-eligible. The signal handlers only stamp the heartbeat when a task starts and finishes, so a task that runs longer than the threshold must say it is still alive, or it can be retried — and run twice — while the first run is still working.

Call `heartbeat()` from the task body's loop:

```python
from background_tasks import heartbeat
from celery import shared_task


@shared_task(name="reports.rebuild")
def rebuild(report_id: int) -> None:
    for chunk in chunks(report_id):
        process(chunk)
        heartbeat()
```

It refreshes `heartbeat_at` on the current execution's row (found through Celery's `current_task`), writing at most once every 30 seconds per task however often you call it, so calling it on every iteration is fine; `heartbeat(force=True)` skips the throttle. Outside a running task it does nothing and returns `False`, so shared helpers can call it unconditionally. It only touches a row that is still `running` — a heartbeat never revives a row the sweep already declared stuck.

A task whose steps are legitimately longer than the global threshold can declare its own, in seconds:

```python
@shared_task(name="exports.full_dump", stuck_after=4 * 3600)
def full_dump() -> None: ...
```

Celery copies extra decorator options onto the task class; the sweep reads `stuck_after` off the task registry of the worker running it (which autodiscovers every module's tasks), and falls back to `SM_BG_TASKS_STUCK_AFTER_SECONDS` / the default for tasks without one. No column or migration is involved, so the threshold always matches the deployed code. A shorter `stuck_after` works too, for tasks that should never take long. Keep any threshold well above 30 seconds, or the heartbeat throttle alone can let a live task look stale.

Not provided: an automatic heartbeat thread. A task that blocks in one long call (a single huge query, an external process) cannot heartbeat from inside it — give it a `stuck_after` that covers the call instead.

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

The worker and beat read the same DB-backed settings the web process does: `scripts/run_worker.py` hydrates `BackgroundTasksSettings` from the database at boot (env still seeds the broker URL), so an admin-edited queue, time limit or `celery_overrides` reaches the worker after a restart. If the database cannot be read the worker starts from env and defaults and logs a warning.

## Routing and queues

A module may ship a light `<pkg>/task_config.py`. It is read **without importing `tasks.py`**, so it must not import heavy dependencies (and does not need celery):

```python
# invoices/task_config.py
TASK_ROUTES = {"invoices.render_*": "heavy", "invoices.notify": {"queue": "mail"}}
QUEUES = {"heavy", "mail"}  # queues this module's tasks run on; default {task_default_queue}
BEAT_SCHEDULE = {...}  # optional; wins over tasks.BEAT_SCHEDULE for the same entry
```

`build_celery` merges `TASK_ROUTES` from every module in sorted package order (the first module wins a pattern clash, with a warning naming both) and sets `task_routes`; web and worker resolve identical routes. The `task_routes_override` setting (JSON `{pattern: queue-or-route-dict}`) is applied over the module routes, so an operator can re-route a task without a code change. The **Routes** table on the Workers admin page lists every effective pattern, its queue, and the module (or `override`) that set it.

### Running a worker for a subset of modules

A worker normally imports every module's `tasks.py`. To keep a light worker from importing a heavy module (torch, GDAL), restrict what it loads:

| Setting / env | Meaning |
|---|---|
| `worker_queues` / `SM_BG_TASKS_WORKER_QUEUES=gpu,default` | import only modules whose `QUEUES` overlap |
| `include_modules` / `SM_BG_TASKS_INCLUDE_MODULES` | always import these packages |
| `exclude_modules` / `SM_BG_TASKS_EXCLUDE_MODULES` | never import these packages (wins over everything) |

Order: exclude, then include, then the queue overlap; with all three empty every module loads. The filter covers both Celery autodiscovery and the eager beat-schedule import. `make worker` passes `-Q $SM_BG_TASKS_WORKER_QUEUES` when the variable is set, so the worker also only consumes those queues. Leave these unset on the web process and on beat: the web process only publishes (it needs every module's routes, which come from `task_config`, not `tasks.py`), and beat must see every schedule.

A publisher that never imported a task can still enqueue it by name: `enqueue_after_commit(db, "reports.build", report_id)` sends it with `send_task`, routed by `task_config`.

`make doctor` warns (`SM028`) when a module's `tasks.py` imports `torch`, `tensorflow`, `ultralytics`, `osgeo`, `rasterio`, `cv2` or `sklearn` at module level. Import them inside the task function instead.

## Worker tuning

Each field defaults to `None`, which keeps Celery's own default; all require a worker restart.

| Field | Celery key |
|---|---|
| `visibility_timeout_seconds` | `broker_transport_options.visibility_timeout` |
| `worker_max_tasks_per_child` | `worker_max_tasks_per_child` |
| `worker_max_memory_per_child_kb` | `worker_max_memory_per_child` |
| `task_reject_on_worker_lost` | `task_reject_on_worker_lost` |
| `task_soft_time_limit` / `task_time_limit` | same |
| `worker_concurrency` | `worker_concurrency` |
| `celery_overrides` | any Celery conf key, applied last; its keys are logged at INFO |

> **Redis and long tasks.** The tasks run with `acks_late`. On a Redis broker a message not acknowledged within the visibility timeout (Celery default: 1 hour) is redelivered, so a task that runs longer than that executes twice. Set `visibility_timeout_seconds` above your longest task.

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
| `task_routes_override`, `worker_queues`, `include_modules`, `exclude_modules`, tuning fields, `celery_overrides` | unset | restart required; see [Routing and queues](#routing-and-queues) and [Worker tuning](#worker-tuning) |
| `task_always_eager` | `False` | runs tasks in-process (test mode) |
| `task_eager_propagates` | `True` | re-raises eager-mode errors |
| `stuck_after_seconds` | `300` | heartbeat-staleness threshold; a task's own `stuck_after` overrides it — see [Long-running tasks](#long-running-tasks-heartbeats-and-stuck-thresholds) |
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
| `background_tasks.sweep_stuck_tasks` | every `stuck_sweep_interval_seconds` | flips `running` rows whose heartbeat is older than their task's `stuck_after` (else `stuck_after_seconds`) to `stuck` |
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
| `task_postrun` | refreshes `heartbeat_at` (between prerun and postrun, only `heartbeat()` from the task body does) |
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

## Reading DB-backed settings in a task

Workers never run the hosting lifespan, so `FileStorageSettings()` (or any `DbBackedSettings`) built inside a task returns pydantic defaults, not what the admin UI saved. Use `background_tasks.settings_for(cls, package)`:

```python
from background_tasks import settings_for
from file_storage.settings import FileStorageSettings


@celery.task
def convert(file_id: int) -> None:
    cfg = settings_for(FileStorageSettings, "file_storage")
```

It reads SYSTEM-scope overrides through the worker's sync session and caches per process for 30 seconds (`ttl=0` always re-reads; `clear_settings_cache()` drops the cache). The underlying sync helper is `settings.hydrate.hydrate_settings_sync`.

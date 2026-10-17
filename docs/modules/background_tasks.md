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

The worker and beat read the same DB-backed settings the web process does: `scripts/run_worker.py` (and the copy `smpy new` scaffolds) calls `background_tasks.runner.build_runner_celery()`, which hydrates `BackgroundTasksSettings` from the database at boot exactly as the web lifespan does. Precedence is env → DB → default: an `SM_BG_TASKS_*` variable that is set wins over a stored value for the same field, and the database supplies everything the environment leaves unset. So an admin-edited queue or time limit reaches the worker after a restart, unless the deployment pins that field in its environment. Because the web process behaves identically, this adds no new trust boundary; still, treat write access to these settings as control of the workers. If the database cannot be read the worker starts from env and defaults and logs a warning.

## Routing and queues

A module may ship a light `<pkg>/task_config.py`. It is read **without importing `tasks.py`**, so it must not import heavy dependencies (and does not need celery):

```python
# invoices/task_config.py
TASK_ROUTES = {"invoices.render_*": "heavy", "invoices.notify": {"queue": "mail"}}
QUEUES = {"heavy", "mail"}  # queues this module's tasks run on; default {task_default_queue}
BEAT_SCHEDULE = {...}  # optional; wins over tasks.BEAT_SCHEDULE for the same entry
```

`build_celery` merges `TASK_ROUTES` from every module in sorted package order (the first module wins a pattern clash, with a warning naming both) and sets `task_routes`; web and worker resolve identical routes. The `task_routes_override` setting (JSON `{pattern: queue-or-route-dict}`; values are restricted to queue names or dicts using only `queue`, `exchange`, `routing_key`, `priority`, and anything else is dropped with a logged error) is consulted before the module routes (Celery gets the router list `[override, modules]`, so an override glob beats a module glob or exact name), so an operator can re-route a task without a code change. The **Routes** table on the Workers admin page lists every effective pattern, its queue, and the module (or `override`) that set it.

### Running a worker for a subset of modules

A worker normally imports every module's `tasks.py`. To keep a light worker from importing a heavy module (torch, GDAL), restrict what it loads. These describe one worker process, so they are **environment variables only** (not settings fields, not stored in the database or shown in the admin UI; a stored value is ignored):

| Env var | Meaning |
|---|---|
| `SM_BG_TASKS_WORKER_QUEUES=gpu,default` | import only modules whose `QUEUES` overlap |
| `SM_BG_TASKS_INCLUDE_MODULES` | always import these packages |
| `SM_BG_TASKS_EXCLUDE_MODULES` | never import these packages (wins over everything) |

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
| `SM_BG_TASKS_CELERY_OVERRIDES` (JSON object, **environment only**) | raw Celery conf keys applied last; its keys are logged at INFO. Never stored in or read from the database, and serializer / `accept_content` / `imports` / `include` / `worker_pool` / `*hijack*` / `security_*` keys are refused with a logged error |

> **Redis and long tasks.** The tasks run with `acks_late`. On a Redis broker a message not acknowledged within the visibility timeout (Celery default: 1 hour) is redelivered, so a task that runs longer than that executes twice. Set `visibility_timeout_seconds` above your longest task.

## Durable events (outbox)

`bus.publish` is in-process: a crash, a restart or a failing handler loses the
event. For side effects that must happen — an invoice email, a search-index
update, a call to another system — subscribe a **durable** handler and publish
durably. This module is the transport; without it `publish_durable` raises
`DurableDeliveryUnavailable`.

```python
# modules/invoices/invoices/module.py
from simple_module_core import DurableContext
from orders.contracts.events import OrderPlaced


class InvoicesModule(ModuleBase):
    def register_event_handlers(self, bus, app=None) -> None:
        # Before any `if app is None: return` — the worker registers with app=None.
        bus.subscribe_durable(OrderPlaced, create_invoice)


async def create_invoice(event: OrderPlaced, ctx: DurableContext) -> None:
    ctx.db.add(Invoice(order_id=event.order_id))  # commits with the delivery mark
```

```python
# in the orders service, inside the request's transaction
await bus.publish_durable(OrderPlaced(order_id=order.id, total=order.total), db)
```

How it is delivered:

- `publish_durable` writes one `background_tasks_outbox` row per durable handler
  **in the caller's session**. A rollback writes nothing, so nothing is delivered.
- After the commit, `background_tasks.dispatch_outbox(ids)` is sent to the broker.
  If that never happens (the process died between commit and publish, or the
  broker was down), the beat task `background_tasks.sweep_outbox` delivers the row
  within `outbox_sweep_interval_seconds` (30 s).
- A worker **claims** a row with one conditional `UPDATE` (`pending → running`,
  `attempts + 1`, `claim_seq + 1`, `locked_until = now + outbox_lease_seconds`);
  on Postgres the candidate select uses `FOR UPDATE SKIP LOCKED`. Two workers
  never claim the same row. A row left `running` past its lease (worker killed)
  goes back to `pending` on the next sweep, or `dead` if that was its last
  attempt.
- The handler runs as `await handler(event, ctx)` in the **scope it was
  published in**, recorded on the row (`scope`): a **tenant** publish runs in
  `tenant_context(<publisher's tenant>)`; a **platform** publish (made inside
  `all_tenants()`) runs inside `all_tenants()`, so tenant-scoped reads see
  every tenant and a write to a `MultiTenantMixin` table needs an explicit
  `tenant_context(id)`; an **unscoped** publish (no tenant bound and not inside
  `all_tenants()`: a public route such as a webhook, a request before tenant
  resolution, a beat job or ordinary task without a tenant) runs as the
  install's `default_tenant` if it has one, and otherwise with **no tenant
  bound**, so under strict isolation a tenant-scoped query fails closed exactly
  as it would have for the publisher. A platform job that means to reach every
  tenant publishes inside `all_tenants()`. The dispatching task's own tenant
  never leaks in. `ctx.attempt` starts at 1.
- **Delivery guarantees.** `ctx.db` is an `AsyncSession` that is committed **in
  the same transaction that marks the row delivered**, and that mark is fenced on
  the claim the worker holds (`claim_seq`, which unlike `attempts` is never
  reset): a handler whose lease expired and was re-run elsewhere has its whole
  session rolled back. Writes through `ctx.db` therefore land **exactly once**.
  For that to hold the handler must not commit `ctx.db` itself: a
  `ctx.db.commit()`, an `async with ctx.db.begin():` block, a commit through
  its connection (`(await ctx.db.connection()).commit()`, as Connection-based
  libraries do), or a library helper that commits raises `HandlerCommitError`
  and fails the attempt, even if the handler swallows it (flush instead if you
  need generated values). Savepoints are fine: `async with
  ctx.db.begin_nested():` (the race-safe insert idiom) releases a savepoint,
  which commits nothing, and its writes land with the delivery. Everything
  outside `ctx.db` — HTTP calls, emails, another session (even one on
  `ctx.db.bind`), a raw DBAPI `COMMIT`, a task you enqueue some other way — is
  **at-least-once**: the handler can run more than once (a retry, a worker killed
  after the side effect but before the commit), so make those steps idempotent,
  e.g. keyed on the event's id or `(event id, handler name)`.
  `ctx.db.on_commit(...)` callbacks run after the commit.
- **Timeouts.** A handler gets `outbox_handler_timeout_seconds`, by default the
  lease minus a safety margin (10 %, at least 5 s: 270 s for the default 300 s
  lease), and never more — so no run outlives its claim and overlaps the rerun a
  reclaim would start. A timeout cancels the handler and counts as a failed
  attempt (`last_error` says so) — also when the handler swallows the
  cancellation and returns late, so never catch `CancelledError` (or bare
  `BaseException`) without re-raising. Raise `outbox_lease_seconds` for slow
  handlers; setting a timeout above the lease's ceiling is refused. The timeout
  is cooperative: **handlers must not block the event loop**. A blocking call
  (`requests`, `boto3`, `time.sleep`, CPU-heavy work) cannot be interrupted, so
  it can outlive its lease and overlap a rerun; run it with
  `await asyncio.get_running_loop().run_in_executor(None, fn, ...)` or use an
  async client.
- On an exception or timeout the session rolls back and the row is retried
  `10 s × 2^(attempts-1)` (capped at 1 h) **after the failure**. After
  `outbox_max_attempts` (8) it is `dead`. A row whose handler the worker does
  not know is retried the same way, because that is usually a **rolling
  deploy**: a new web pod published for a handler an old worker does not have
  yet, and a later worker will. Rename a handler only together with `name=`,
  or its undelivered rows go `dead` once their attempts run out. A payload that
  no longer validates, or an invalid tenant id, goes `dead` straight away with
  the reason in `last_error`.
- **One clock.** Every outbox timestamp — the publisher's `next_attempt_at`,
  claims, leases, reclaims, admin retries — is read from the database
  (`clock_timestamp()` on Postgres), so clock skew between web pods and workers
  cannot make a fresh row look not-yet-due or shorten a lease. SQLite has no
  server; every process sharing the file is on one host and uses its clock.
- Delivered rows are deleted by `purge_old_executions` after `retention_days`. `dead` rows are never purged: they wait on the admin page to be retried or discarded.

Handler **names** are the delivery key — by default the handler's import path
(`invoices.module.create_invoice`); pass `name=` to `subscribe_durable` to pin it
before renaming the function. Events must be `@dataclass` classes whose fields
pydantic can put in JSON (str/int/float/bool/`Decimal`, `UUID`, `datetime`/`date`,
`Enum`, nested dataclasses, lists, dicts, `X | None`); this is checked at
`subscribe_durable`.

**Worker side.** The Celery tasks are synchronous; each dispatch runs on a
long-lived outbox event loop owned by the calling worker thread (a daemon
thread, started on first use; under `prefork` one per child, under `threads`
one per Celery thread, so concurrent deliveries in one process never share a
loop). Each loop has its own async engine on the same database URL as
`sync_db`, with a small pool (1 + 2 overflow: a thread delivers one row at a
time) and the host's tenancy policy — so budget up to three database
connections per worker thread. The worker builds its own `EventBus` once per
process by calling every installed module's `register_event_handlers(bus, None)`.
That bus carries a durable transport too, so a durable handler can itself
`publish_durable(..., ctx.db)`: the new rows commit with the handler's delivery
and are handed to `dispatch_outbox` after that commit. A module whose
`register_event_handlers` fails without an app is logged once per worker process
(its durable events then retry until a worker that knows them delivers them, or
they go `dead`). A worker started limited to a subset of modules (queue or
module filters) still knows every module's durable handlers: the bus comes from
discovery, not from the imported `tasks.py`. Use the `prefork` or `threads`
pool: a dispatch blocks its worker thread while its outbox loop runs it, which
under `gevent`/`eventlet` would block the hub.

**Deploys.** Ship workers and web pods with the same handlers. During a rolling
deploy, events for a handler only the new code has are retried with backoff
until a new worker claims them; with the defaults a row has about 21 minutes of
attempts (8 attempts, backoff 10 s to 640 s) before it goes `dead`, so a
rollout slower than that leaves dead rows to retry from the admin page. A
removed module's undelivered rows likewise end `dead`; discard them there.

**Eager mode** (`task_always_eager`, tests and single-process dev) delivers on
the web process's own engine — no worker needed: a request's rows from its
`on_commit`, and rows written in any other session (a CLI script, a startup
hook, a durable handler's `ctx.db`) from that session's commit, as a task on
the running loop. Nothing sweeps in eager mode: a failed delivery stays
`pending` until a worker runs, or until it is retried from the admin page.

**SQLite.** A durable handler holds SQLite's single write lock from its first
write until the delivery commits; keep handlers that write short there, or
concurrent web writes wait (and fail after the 5 s busy timeout).

The admin page `/admin/background-tasks/outbox` (linked from the executions
list) shows pending, running and dead rows with their last error; dead rows can
be **retried** (back to `pending`, attempts reset; the fencing token is not) and pending or dead rows
**discarded**.

Unlike the executions screens, the outbox admin is **tenant-scoped**: a platform
admin (global `admin` role) sees every tenant's rows, while any other principal
holding `background_tasks.view`/`manage` (a tenant role granted it in the role
editor) sees and acts on only its active tenant's rows — another tenant's row id
answers 404. Outbox rows carry event payloads, hence the tighter rule.

## Routes

### Admin API

All require `background_tasks.view`; retry additionally needs `background_tasks.manage`.

| Method + path | Body / response | Notes |
|---|---|---|
| `GET /api/background_tasks/admin/executions` | `?status=&task_name=&page=&per_page=` → `TaskExecutionListResponse` | per_page max 200 |
| `GET /api/background_tasks/admin/executions/{execution_id}` | → `TaskExecutionDetail` | 404 if missing |
| `POST /api/background_tasks/admin/executions/{execution_id}/retry` | → `TaskExecutionDetail` | 409 unless status is `failed` or `stuck` |
| `GET /api/background_tasks/admin/workers` | → `WorkerSnapshot` | live ping; consumed by the `Workers` page |
| `GET /api/background_tasks/admin/outbox` | `?status=&page=&per_page=` → `OutboxListResponse` | undelivered rows (pending, running, dead) and per-status counts |
| `POST /api/background_tasks/admin/outbox/{id}/retry` | → `OutboxItem` | `manage`; 409 unless `dead`; resets attempts and dispatches after commit |
| `DELETE /api/background_tasks/admin/outbox/{id}` | 204 | `manage`; 409 for a `running` row |

### View

| Method + path | Inertia component | Permission |
|---|---|---|
| `GET /admin/background-tasks/` | `BackgroundTasks/Index` | `background_tasks.view` |
| `GET /admin/background-tasks/workers` | `BackgroundTasks/Workers` | `background_tasks.view` |
| `GET /admin/background-tasks/outbox` | `BackgroundTasks/Outbox` | `background_tasks.view` |
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

`OutboxMessage` (table `background_tasks_outbox`) — one row per (durable event, handler); see [Durable events](#durable-events-outbox).

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `event_key` / `handler_name` | `str(255)` | `<module>.<EventClass>` and the durable handler's name |
| `payload` | JSON | the serialised event |
| `tenant_id` | `str(50) \| None` | publisher's tenant; plain column like `TaskExecution.tenant_id` |
| `status` | `str(20)` | `pending` `running` `delivered` `dead` |
| `attempts` | `int` | bumped on claim; also the claim's fencing token |
| `next_attempt_at` / `locked_until` | `datetime` | backoff and lease |
| `last_error` | `str \| None` | exception line, then the traceback's tail |
| `created_at` / `delivered_at` | `datetime` | |

## Settings

DB-backed; defaults are in `BackgroundTasksSettings`. Several are marked `requires_restart=True` because Celery reads them at process start.

| Field | Default | Notes |
|---|---|---|
| `broker_url` | `redis://localhost:6379/0` | restart required; rejected as `localhost` in production |
| `result_backend` | `redis://localhost:6379/1` | restart required; `broker_url`/`result_backend` must use a plain scheme (`redis://`, `amqp://`, `db+sqlite://`): dotted or `module:Class` names are refused because Celery imports them |
| `task_default_queue` | `"default"` | restart required |
| `task_routes_override`, tuning fields | unset | restart required; see [Routing and queues](#routing-and-queues) and [Worker tuning](#worker-tuning) |
| `task_always_eager` | `False` | runs tasks in-process (test mode) |
| `task_eager_propagates` | `True` | re-raises eager-mode errors |
| `stuck_after_seconds` | `300` | heartbeat-staleness threshold; a task's own `stuck_after` overrides it — see [Long-running tasks](#long-running-tasks-heartbeats-and-stuck-thresholds) |
| `stuck_sweep_interval_seconds` | `60` | beat cadence for the stuck sweep |
| `purge_interval_seconds` | `86_400` | beat cadence for old-row purge |
| `retention_days` | `14` | how long to keep terminal rows; range 1-3650 |
| `max_retries` | `3` | informational; tasks define their own policies; range 0-100 |
| `outbox_max_attempts` | `8` | durable-event delivery attempts before `dead`; range 1-100 |
| `outbox_sweep_interval_seconds` | `30` | restart required; beat cadence of `sweep_outbox` |
| `outbox_lease_seconds` | `300` | how long a claimed delivery may run before another worker reclaims it; range 10-86400 — keep it above your slowest durable handler |
| `outbox_handler_timeout_seconds` | unset | per-attempt handler timeout; unset means the lease minus a safety margin (10 %, at least 5 s), which is also the most it may be set to |

Bootstrap env-var equivalents (`SM_BG_TASKS_*`) only seed pydantic defaults at first boot — once a value lives in the DB, it's authoritative.

## Permissions

| Code | Purpose |
|---|---|
| `background_tasks.view` | list + detail + worker snapshot |
| `background_tasks.manage` | retry failed / stuck tasks; retry or discard outbox rows |

## Menu

| Label | URL | Icon | Section | Group | Order | Roles |
|---|---|---|---|---|---|---|
| `Background Tasks` | `/admin/background-tasks` | `activity` | `SIDEBAR` | `Administration` | `120` | `["admin"]` |

## Beat schedule (built-in)

| Task | Schedule | What |
|---|---|---|
| `background_tasks.sweep_stuck_tasks` | every `stuck_sweep_interval_seconds` | flips `running` rows whose heartbeat is older than their task's `stuck_after` (else `stuck_after_seconds`) to `stuck` |
| `background_tasks.purge_old_executions` | every `purge_interval_seconds` | deletes terminal rows, and delivered outbox rows, older than `retention_days` |
| `background_tasks.sweep_outbox` | every `outbox_sweep_interval_seconds` | reclaims expired outbox leases and delivers every due outbox row |

`background_tasks.dispatch_outbox(ids)` is not scheduled: it is sent after each commit that wrote outbox rows.

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
- `BackgroundTasks/Outbox.tsx` — undelivered durable events with retry / discard.
- Components: `ExecutionRow.tsx`, `RetryConfirmDialog.tsx`.

## Locales

Top-level keys in `background_tasks/locales/en.json`: `index`, `filters`, `status` (per-state labels), `table`, `detail`, `retry_dialog`, `toasts`, `outbox`.

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

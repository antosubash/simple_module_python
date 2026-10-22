# Runtime batch 2: task progress, retained logs, Sentry, leases, in-process outbox

Approved 2026-10-21 for #536, #537, #538, #539, #565 with the defaults below.

## #536 Progress and owner-scoped status (background_tasks)

- `TaskExecution` gains `progress_current: int|None`, `progress_total: int|None`,
  `progress_message: str(255)|None`, `progress_phase: str(64)|None`, `owner_user_id: str(64)|None`
  (indexed). All progress fields go in `__audit_exclude_fields__`.
- Owner stamping: `stamp_owner(headers)` next to `stamp_tenant` (`tenant_context.py`), header
  `sm_owner_id`, set from `current_user_id` in a request and propagated by tasks that enqueue tasks;
  `on_task_publish` writes the column.
- `heartbeat(*, progress=(i, n), message=None, phase=None, force=False)`: latest progress buffered
  under the existing throttle; `i == n` forces a write.
- `GET /api/background_tasks/tasks/{celery_task_id}/status` in a new router without `PERM_VIEW`:
  owner + active tenant (or tenancy off) → `TaskStatusDTO` (status, progress fields, timestamps,
  sanitized error type; never traceback/args/result); anyone else 404; holders of `PERM_VIEW` bypass
  the owner check.
- Progress bar on `pages/Detail.tsx`. One migration (branch label `background_tasks`, off
  `e878882924e7`).

## #537 Retained task and app logs

- Hosting: `LogSink` Protocol (`emit_batch(records)`) + `QueueSinkHandler` (QueueHandler + listener
  thread; batch 200 / 1 s; bounded queue, drop-and-count when full; level threshold; skips its own
  logger and `sqlalchemy.*`). Redaction filter masks Authorization, Cookie, password, token,
  `secret=` before queueing.
- background_tasks: table `background_tasks_log_record` (id, ts, level int, logger, message ≤4 KB,
  task_id, job_id, tenant_id, correlation_id, extra JSON), indexes (task_id, ts), (ts), (level, ts);
  no MultiTenantMixin (like TaskExecution; admin views filter tenant_id). DB sink via
  `sync_session`, audit excluded; installed in `on_startup` and worker init.
- DB-backed settings: `log_sink_enabled=False`, `log_sink_level="INFO"`, `log_retention_days=7`;
  purge pass in `purge_old_executions`.
- UI: Logs tab on task detail (level filter, #513 pagination) and an admin `Logs.tsx` search page
  with a menu item; `PERM_VIEW`.
- Migration chains on #536's.

## #538 Optional Sentry

- `simple_module_hosting[sentry]` extra (`sentry-sdk[fastapi,celery]`); `simple_module_hosting/
  sentry.py` `init_sentry(process: "web"|"worker")` returns before importing the SDK when
  `SM_SENTRY_DSN` is unset.
- Env only (secret + pre-DB process wiring): `SM_SENTRY_DSN`, `SM_SENTRY_ENVIRONMENT` (default
  `SM_ENVIRONMENT`), `SM_SENTRY_TRACES_SAMPLE_RATE` (default 0.0).
- Web: called in `create_app` before middleware; worker: on `worker_process_init` in
  background_tasks.
- Event processor tags request_id (correlation id), tenant, user id (never email), module, task.
  `before_send` scrubs Authorization/Cookie/Set-Cookie/X-CSRF-Token/X-Api-Key headers, `token`/`code`
  query values and request bodies; `send_default_pii=False`. DSN never logged.

## #539 Distributed TTL leases

- Core `simple_module_core/leases.py`: `LeaseBackend` Protocol (acquire / refresh / release /
  semaphore_acquire); `lease(name, ttl, owner=None)` handle (`.token`, `.fence`, `refresh()`,
  async context manager with wait/blocking); `semaphore(name, slots, ttl)`;
  `InProcessLeaseBackend`; `configure_leases(backend)` / `get_leases()` module-global (workers have
  no app.state).
- Redis backend (hosting): `SET NX PX`; Lua compare-and-set refresh/release on the token;
  semaphore ZSET scored by expiry using Redis `TIME`; `INCR {name}:fence` fencing token.
- DB backend: table `sm_lease(name, slot, holder, fence, expires_at)`, unique (name, slot), DB clock,
  in `simple_module_db` (branch label `leases`).
- Selection: Redis when `SM_REDIS_URL` is set, else DB table, else in-process. An expired owner
  cannot release.

## #565 In-process outbox

- background_tasks setting `outbox_mode: Literal["celery","inprocess"]` (restart-required), default
  `"celery"` but resolves to `"inprocess"` automatically when `task_always_eager` is set.
- In-process: `on_startup` starts an asyncio loop per web process running `dispatch(ids=None)` every
  `outbox_sweep_interval_seconds` with jitter; `on_shutdown` cancels and drains. Eager `schedule`
  path kept.
- Celery import moved inside `WorkerOutboxTransport.schedule`.
- `tasks.py` stuck sweep and purge read `retention_days` etc. via `load_runner_settings()` (DB),
  not raw env.

## Slices

Wave 1 in parallel: A #539 (core/hosting/db + `leases` migration), B #538 (hosting sentry.py + one
hook in background_tasks worker init), C #536 (background_tasks models/signals/tenant_context/
heartbeat/schemas/api_status/Detail.tsx + migration), E #565 (outbox_transport/module/tasks/settings).
Wave 2: D #537 after C. Update `host/tests/test_migration_graph.py` for new heads/labels.

# Enhancement batch #447–#459: design

Date: 2026-10-15. Tracking issue: #460.

Issues covered:
- #447: background_tasks task routing.
- #448: background_tasks Celery worker tuning.
- #450: per-worker task module subset.
- #454: file_storage multipart, presigned, resumable uploads.
- #455: personal access tokens and service API keys.
- #456: OpenAPI export.
- #458: Postgres extensions and column types.
- #459: durable event delivery (outbox).

## Delivery

| PR | Issues | Depends on |
|---|---|---|
| 1 | #447, #448, #450 (Celery config) | — |
| 2 | #459 (outbox) | PR 1 |
| 3 | #456 (OpenAPI export) | — |
| 4 | #455 (new `api_tokens` module) | — |
| 5 | #454 (multipart uploads) | — |
| 6 | #458 (Postgres extensions and types) | — |

New doctor codes:
- SM028: a `tasks.py` imports a heavy package at module level.
- SM029: a module declares Postgres extensions but the database is SQLite.

---

## PR 1: Celery routing, tuning, per-worker subset (#447, #448, #450)

### Where routes are declared: `<pkg>/task_config.py`
A module may ship a light `task_config.py`. It must not import heavy dependencies and should not import celery. It exports:
- `TASK_ROUTES: dict[str, str | dict]`: Celery `task_routes` entries. Glob patterns are allowed, and a value may be a queue name or a full route dict.
- `QUEUES: set[str]`: the queues this module's tasks run on. If omitted, it defaults to `{task_default_queue}`.
- `BEAT_SCHEDULE: dict` (optional). `BEAT_SCHEDULE` in `tasks.py` keeps working. When both define the same entry, `task_config` wins.

Routes must be known without importing `tasks.py`. Otherwise the per-worker subset (#450) would have to import every heavy module just to read its routes.

### #447 routing
- `build_celery` collects `TASK_ROUTES` from every module's `task_config` in sorted package order. On a pattern clash it keeps the first module's entry and logs a warning that names both modules.
- A new setting, `task_routes_override` (JSON dict, `requires_restart`, Celery group), is applied over the module routes. It lets an operator re-route tasks without changing code.
- The merged mapping is set as `conf.task_routes`. The web process and the worker both call `build_celery`, so both resolve identical routes.
- A new "Routes" table on the Workers admin page lists each pattern with its queue and the module that set it.

### #448 worker tuning
New `BackgroundTasksSettings` fields, all with `requires_restart` and group Celery, and all defaulting to `None` (keep Celery's default):
- `visibility_timeout_seconds`, which goes to `broker_transport_options.visibility_timeout`;
- `worker_max_tasks_per_child`;
- `worker_max_memory_per_child_kb`;
- `task_reject_on_worker_lost`;
- `task_soft_time_limit`;
- `task_time_limit`;
- `worker_concurrency`.

Raw Celery conf comes from the environment-only `SM_BG_TASKS_CELERY_OVERRIDES` (JSON). It is not a settings field, because those are DB-backed and admin-editable. Keys that choose serializers or load code are refused. It is applied last with `conf.update`, and its keys are logged at INFO. The docs warn that with Redis and `acks_late`, tasks longer than 1 h need `visibility_timeout_seconds`.

### #450 per-worker module subset
- New settings:
  - `worker_queues` (env `SM_BG_TASKS_WORKER_QUEUES`, comma-separated);
  - `include_modules`;
  - `exclude_modules`.
- Which packages a process imports `tasks.py` for, applied in this order:
  1. A package in `exclude_modules` is never imported.
  2. Otherwise, a package in `include_modules` is always imported.
  3. If `worker_queues` is set, a package is imported only when its `QUEUES` overlap `worker_queues`.
  4. Otherwise every package is imported, as today.
- The filter applies both to `autodiscover_tasks` and to the eager beat-schedule import.
- `make worker` passes `-Q $(SM_BG_TASKS_WORKER_QUEUES)` when the variable is set.
- `enqueue_after_commit(db, task_or_name, ...)` accepts a task name and sends it with `celery.send_task`. That lets a publisher enqueue a task it never imported. The docs cover this pattern.
- **SM028** (warn): a module's `tasks.py` has a top-level import of `torch`, `tensorflow`, `ultralytics`, `osgeo`, `rasterio`, `cv2` or `sklearn`. The check uses AST and does not import the module.

### Worker settings fix (found while designing)
`scripts/run_worker.py` builds `BackgroundTasksSettings()` from env only, so DB-backed settings never reach the worker at boot. The fix hydrates them from the DB the same way task bodies do (`settings_for`), using the same hydration as the web lifespan (a stored DB value beats the same field's env var, exactly as it does in the web process).

### Stray patch
Four unverified review edits to code merged in #463:
- after-commit `mark_written`;
- retry `_fail_unsent`;
- stuck threshold `max(1, …)`;
- file_storage 416 `Cache-Control`.

Each one is reproduced with a failing test first. Kept only if the test fails before the fix.

---

## PR 2: Durable outbox (#459)

### Core (`simple_module_core.events`)
- `bus.subscribe_durable(EventType, handler, *, name=None)`. `name` defaults to `f"{handler.__module__}.{handler.__qualname__}"` and must be stable, because delivery state is keyed by it.
- `await bus.publish_durable(event, db)` hands off to `bus.durable_transport`, a `DurableTransport` protocol with `async enqueue(event, handler_names, db)`. If no transport is installed it raises `DurableDeliveryUnavailable`.
- `publish` and `publish_nowait` are unchanged.
- Events must be JSON-serializable dataclasses. UUID, datetime, Enum and nested dataclasses are supported.

### background_tasks transport and dispatcher
- Table `background_tasks_outbox`. Columns:
  - `id`, `event_key`, `payload` (JSON), `handler_name`, `tenant_id`;
  - `status` (pending | running | delivered | dead);
  - `attempts`, `next_attempt_at`, `last_error`;
  - `created_at`, `delivered_at`.
- `enqueue` writes one row per durable handler in the caller's session. A rollback therefore writes nothing.
- `db.on_commit` enqueues `background_tasks.dispatch_outbox(ids)`. A beat sweep, `background_tasks.sweep_outbox`, runs every 30 s and picks up due rows, which covers a crash between commit and publish.
- Claiming: a conditional UPDATE from `pending` to `running` with a lease. On Postgres it uses `FOR UPDATE SKIP LOCKED`. A row stuck in `running` past its lease goes back to `pending`.
- Handlers are called as `async handler(event, ctx)`.
  - `ctx.db` is a session that commits in the same transaction that marks the row delivered. The handler's DB effects are therefore exactly-once.
  - `ctx.attempt` is the current attempt number.
  - Handlers run inside `tenant_context(row.tenant_id)`.
- The worker builds its own `EventBus` by calling every module's `register_event_handlers(bus, None)`.
- On failure, the next attempt waits `10 s × 2^(attempts-1)`, capped at 1 h. After `outbox_max_attempts` (default 8) the row becomes `dead`.
- New admin page `/admin/background-tasks/outbox` lists pending and dead rows and offers retry (dead → pending, attempts reset) and discard.
- Purge: delivered rows older than `retention_days` are removed by the existing purge task.

### Acceptance
- A handler that fails twice and then succeeds ends with exactly one successful delivery.
- An event published in a transaction that rolls back is never delivered.

---

## PR 3: OpenAPI export (#456)

- New `HostSettings` fields, read before the app is built, all `requires_restart`:
  - `api_title` (default `"SimpleModule"`);
  - `api_version` (default: the host distribution's version, falling back to `"0.0.0"`);
  - `api_description`;
  - `openapi_public` (default False, env `SM_OPENAPI_PUBLIC`).
- The schema is served at `/api/openapi.json` instead of `/openapi.json`. In development it is always served. Otherwise it is served only when `openapi_public` is true. The auth framework public prefixes follow the same rule.
  - **Behaviour change** (CHANGELOG): the bare `/openapi.json` is removed. It used to be served in production too.
- View routers and admin-view routers are mounted with `include_in_schema=False`. A custom `openapi()` also drops any path not under `/api/`.
- `generate_unique_id_function` produces operationIds `<module>_<endpoint function name>`, with the module taken from the route's first tag in snake_case.
  - On a duplicate, the method and path are appended and a warning is logged.
  - A test asserts uniqueness across the shipped modules.
- `smpy openapi export [--out openapi.json] [--module NAME ...]` builds the app in process with `create_app` and does not start a server. `simple_module_hosting` is imported lazily, which keeps `test_no_framework_deps` passing. It reads host settings from the DB when reachable; otherwise it warns and uses env and defaults. There is also a `make openapi` target.
- Docs give CI recipes for a hey-api TypeScript client and a Dart client (openapi-generator `dart-dio`).

---

## PR 4: `api_tokens` module (#455)

### Tokens
- Formats: `smpat_<base62 of 32 random bytes>` (personal) and `smsk_<…>` (service key). Only `sha256(secret)` is stored, plus an 8-character display prefix. The secret is shown once.
- Table `api_tokens_token` (AuditMixin, MultiTenantMixin). Columns:
  - `id`, `kind` (personal | service), `name`, `prefix`, `token_hash` (unique);
  - `owner_user_id` (null for service);
  - `scopes` (JSON, non-empty), `roles` (JSON, service only);
  - `expires_at`, `last_used_at`, `revoked_at`.
- Create and revoke produce audit-log entries through `AuditMixin`.

### Resolution
- The resolver is appended to `app.state.auth.principal_resolvers` (`depends_on` auth, users).
- The users provider, and the keycloak provider if it applies, returns `None` immediately for bearer values with the `smpat_` or `smsk_` prefix. That avoids a wasted token-table lookup and lets the resolver claim the token.
- Each request does one indexed lookup by hash with no cache. A revoked or expired token, or an inactive or disabled owner, gets `None`, which means 401.
- `last_used_at` is written at most once every 5 minutes, through a conditional UPDATE in a short separate session.
- `UserContext` gains `auth_kind: str = "session"` and `scopes: list[str] | None = None`. Both are wired through `from_user`, `to_session_dict` and `from_session_dict`.

### Scope cap
- `resolve_principal_permissions` intersects the resolved set with `scopes` whenever `scopes` is not None. It expands `*` against the scope list.
- `require_permission` (auth) and `RequiresPermission` (hosting) skip the admin-role shortcut when `scopes` is not None.
- At creation, scopes must be a subset of the creator's current permissions. On every request, the cap is applied on top of the owner's live grants, so demoting the owner shrinks the token immediately.
- Service keys: `id = f"svc:{token_id}"`, so they get no direct grants. Roles are chosen at creation and `admin` is forbidden. The key is pinned to its `tenant_id`.
- A request authenticated with a token (`auth_kind != "session"`) cannot create, list or revoke tokens.

### UI and permissions
- Permissions:
  - `api_tokens.use`: own PATs. Default role `user`, and the tenant member role.
  - `api_tokens.manage`: all tokens and service keys. Admin.
- A `USER_DROPDOWN` item "API tokens" (order 980) leads to `/api-tokens`, where users list, create and revoke. Creating a token takes:
  - a name;
  - a scope picker limited to the creator's own permissions;
  - an expiry preset no longer than the setting `max_lifetime_days` (default 365).
- `/admin/api-tokens` (`ADMIN_SIDEBAR`, Access group) lists every token, creates service keys, and revokes.
- The cookie-authenticated mutation endpoints use `RequiresCsrf`.
- Release: the new PyPI name needs a pending publisher registered by hand.

### Acceptance
A PAT with scope `X.read` can GET but not POST. It still works after a server restart, and stops working on the next request after it is revoked.

---

## PR 5: Multipart and resumable uploads (#454)

### Backend contract
- An optional capability, `supports_direct_upload: bool`, with these methods:
  - `create_multipart(key, content_type) -> upload_id`;
  - `presign_part(key, upload_id, part_no, ttl) -> url`;
  - `list_parts(key, upload_id) -> list[Part(no, etag, size)]`;
  - `complete_multipart(key, upload_id, parts)`;
  - `abort_multipart(key, upload_id)`;
  - `presigned_put_url(key, ttl, content_type)`;
  - `head(key) -> ObjectInfo(size, etag)`.
- Backends without the capability raise `NotSupportedError`.
- S3: parts are uploaded directly with presigned `upload_part` URLs.
  - A new setting, `s3_public_endpoint_url`, is the browser-facing endpoint used for presigning. It falls back to `s3_endpoint_url`.
  - The origin is added to CSP `connect-src` through `CspSourceRegistry.add_provider`.
  - The docs give the bucket CORS rule: allow PUT and expose `ETag`.
- Filesystem: parts go through the app with `PUT /api/file-storage/uploads/{id}/parts/{n}` and are stored under `root/.multipart/<upload_id>/<n>`. A body-limit rule allows part size plus slack. Completing concatenates the parts into the final key.

### Sessions and API
- Table `file_storage_upload_session` (AuditMixin, MultiTenantMixin). Columns:
  - `id`, `key`, `filename`, `content_type`, `total_size`, `part_size`, `backend_upload_id`;
  - `status` (active | completed | aborted), `public`, `expires_at`.
- The backend's `list_parts` is the source of truth for completed parts.
- Endpoints (under `/api/file-storage`, permission upload):
  - `POST /uploads`: validates the type, the size against `max_direct_upload_bytes` (default 10 GiB) and the quota. It picks `part_size`: 16 MiB, grown so the upload needs no more than 10,000 parts. It returns the session.
  - `GET /uploads/{id}`: the session plus the completed parts, for resuming.
  - `POST /uploads/{id}/part-urls` with `{parts: [n…]}`: URLs for those parts.
  - `POST /uploads/{id}/complete` with `{parts: [{n, etag}]}`: completes the upload, checks that `head` size equals the declared size, creates the `StoredFile`, and publishes `FileUploaded`.
  - `DELETE /uploads/{id}`: aborts.
- `StoredFile.checksum_sha256` becomes nullable (migration).
  - Multipart uploads are created with a null checksum.
  - When background_tasks is installed, `file_storage.compute_checksum` streams the object and fills the checksum in.
  - The UI shows "—" while the checksum is null.

### Janitor
- `file_storage/tasks.py`, hourly beat `file_storage.reap_stale_uploads`, runs only when background_tasks is installed. It aborts expired sessions (default TTL 24 h) and, on S3, orphan multipart uploads older than 2 × TTL.
- Without background_tasks, `POST /uploads` aborts the caller's own expired sessions.

### Browser
- `upload-queue.ts` uses the session flow when the file size is above `direct_upload_threshold_bytes` (default 64 MiB). It uploads 4 parts at a time, retries each part with backoff, and shows progress per byte.
- The session id is stored in `localStorage`, keyed by the file name, size and `lastModified`. After a reload, the user selects the same file again and the upload resumes from the completed parts. Browsers cannot keep file handles across a reload.

### Acceptance
A 5 GB file uploads in parts straight to MinIO, resumes after a reload once the file is selected again, and ends up as a normal `StoredFile`.

---

## PR 6: Postgres extensions and column types (#458)

- New `ModuleBase.db_extensions(self) -> list[str]` hook, defaulting to `[]`, beside `locale_dirs`. Names must match `^[a-z][a-z0-9_]*$`.
- New `simple_module_db.migrations.ensure_db_extensions(connection, modules)`:
  - on Postgres, it runs `CREATE EXTENSION IF NOT EXISTS "<name>"`;
  - on SQLite, if any extension is requested, it raises `UnsupportedDatabaseError` naming the module and the extensions;
  - in offline mode, it emits the statements.
- It is called in `env.py` (host and scaffold template) before `run_migrations()`. The setup wizard runs that same env.py.
- The Postgres test fixtures re-create the extensions after each per-test schema reset.
- `simple_module_db.types.LTree` (`LTREE`) and `TSVector` (`TSVECTOR`) fall back to `TEXT` on SQLite, so `create_all` works there. `render_item` renders them with the correct imports.
- A `postgres` pytest marker is registered by the `simple_module_test` plugin. Those tests are skipped unless the test DB is Postgres.
- **SM029** (info): a module declares `db_extensions` and the database is SQLite.
- Acceptance is a Postgres-only test. It autogenerates a migration for a throwaway `LTree` model, then runs upgrade, downgrade and upgrade against Postgres. No shipping module gains an ltree column.

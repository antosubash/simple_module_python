# Environment variables

Most deployments only set a few variables.

- `SM_DATABASE_URL` selects the database. SQLite is the default.
- `SM_REDIS_URL` connects shared rate limiting and background tasks to Redis when used.
- `SM_USERS_BOOTSTRAP_*` seeds the first local accounts. See [Users module](#users-module) for the specific variables.
- `SM_ENVIRONMENT`, `SM_DEBUG` and `SM_VITE_DEV_URL` describe how the process runs.

Edit deployment settings such as mail credentials, feature flags and storage
backends in the admin UI. The tables below cover the framework, bundled modules
and repository tools. See [Configuration](/guide/configuration) for an overview.

## Framework

| Variable | Default | Notes |
|---|---|---|
| `SM_DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | Async database URL. For PostgreSQL, use `postgresql+asyncpg://user:pw@host:5432/db`. Relative SQLite paths resolve against the project root. |
| `SM_REDIS_URL` | unset | Enables shared Redis rate limits and leases and seeds both the Celery broker and result backend. Without it the host uses in-process rate limits and database-backed leases. |
| `SM_ENVIRONMENT` | `development` | `development` and `testing` bypass production secret checks. Any value other than `development` enables strict module discovery. |
| `SM_DEBUG` | `false` | Enables debug mode, including tracebacks in HTTP responses. |
| `SM_VITE_DEV_URL` | `http://localhost:5050` | Vite HMR origin for development. Scaffolded apps also derive the Vite dev server port and origin from this URL. |
| `SM_VITE_PORT` | `5050` | Vite dev server port in this repository's own host. Set `SM_VITE_DEV_URL` to match when changing it. |
| `SM_SECRET_KEY` | generated when unset | Session signing key. If unset, the framework reuses the stored key or generates and saves one. A fresh DB without the settings table uses a temporary key until persistence is possible. An explicit key wins and stays out of the DB. Production rejects the literal placeholder `change-me-in-production`. |
| `SM_MODULES_ENABLED` | unset | JSON array of module names. Unset loads all installed modules. An empty array loads none. |
| `SM_PROJECT_ROOT` | discovered | Overrides project-root discovery for `.env` and relative SQLite paths. Otherwise discovery walks up from the working directory and stops at repository or home-directory boundaries. |

The repository's Docker entrypoint generates and exports a process-local
signing key when absent. This bypasses the framework's DB-backed key, so set a
stable key when using that entrypoint and sharing sessions across restarts or replicas.

### Module-enabled allow-list

```bash
export SM_MODULES_ENABLED='["Users","Dashboard"]'
```

Use the module's `ModuleMeta.name`. Matching is case-insensitive. Include any
required dependencies and restart after changing the allow-list. A
comma-separated string fails settings validation.

## Host settings (`HostSettings`)

Host settings resolve **env → DB → default**. The fields appear under Host in
the admin settings editor. A boot setting takes effect after restart. Runtime
settings can change live unless pinned by the environment. See [Settings](/framework/settings).

| Variable | Default | Notes |
|---|---|---|
| `SM_MULTI_TENANT` | `false` | Enable tenant isolation. Restart required. |
| `SM_DEFAULT_TENANT` | `""` | Fixed tenant in single-tenant mode. Blank uses the default tenant ID for new rows. Restart required. |
| `SM_TENANT_HEADER` | `""` | Tenant lookup header in multi-tenant mode. Blank disables header lookup. Restart required. |
| `SM_AUTH_PROVIDER` | `users` | Auth provider to activate when both Users and Keycloak are installed. Restart required. |
| `SM_AUTH_PUBLIC_PATHS` | `[]` | JSON array of anonymous-access path prefixes. Modules can declare method-aware public routes with `register_public_routes`. Restart required. |
| `SM_I18N_DEFAULT_LOCALE` | `en` | Default locale. Must be in the supported locales. Restart required. |
| `SM_I18N_SUPPORTED_LOCALES` | `["en"]` | JSON array of enabled locales. Restart required. |
| `SM_I18N_COOKIE_NAME` | `locale` | Locale preference cookie name. Restart required. |
| `SM_MAINTENANCE_MODE` | `false` | Serve a 503 to everyone except admins. Runtime. |
| `SM_MAINTENANCE_MESSAGE` | `""` | Optional maintenance notice. Runtime. |
| `SM_PUBLIC_BASE_URL` | `""` | Shared public origin for canonical and `og:url` links, account emails and invitation links. `users.base_url` and `tenants.public_base_url` inherit it when blank. Never derived from the request `Host`. Runtime. |
| `SM_LOGIN_REDIRECT_URL` | `/dashboard/` | Where every auth provider sends a user after sign-in; falls back to another view when the Dashboard module is absent. Runtime. |
| `SM_NATIVE_LINK_PREFIXES` | `[]` | JSON array of path prefixes whose links use full browser navigation. Runtime. |
| `SM_LOG_LEVEL` | `INFO` | Application logging threshold. Restart required. |
| `SM_LOG_FORMAT` | `json` | Structured `json` or readable `text`. Restart required. |
| `SM_TRUSTED_PROXY` | unset | Comma-separated trusted proxy IPs or CIDRs. `*` trusts any peer. A trusted TLS terminator can supply the client IP and original request scheme for logs and auth callbacks. Restart required. |
| `SM_FORWARDED_HOST_ALLOWLIST` | `[]` | JSON array of allowed forwarded hosts, such as `["app.example.com","*.example.org"]`. Entries may include ports. Requires `SM_TRUSTED_PROXY`. Restart required. |
| `SM_SESSION_COOKIE_SECURE` | unset | `Secure` flag for both the session cookie and the users auth cookie. Unset enables it outside development and testing. Restart required. |
| `SM_MAX_REQUEST_BODY_BYTES` | `10485760` | Global request body limit in bytes. `0` disables the guard. Applies live after a settings save. |
| `SM_RATE_LIMIT_PUBLIC` | `120/minute` | Per-IP budget for anonymous requests to public routes. Blank or `off` disables it. Applies live after a settings save. |
| `SM_RATE_LIMIT_AUTHENTICATED` | `""` | Per-IP budget for signed-in traffic, using the same syntax. Blank disables it. Applies live after a settings save. |
| `SM_API_TITLE` | `SimpleModule` | OpenAPI title. Restart required. |
| `SM_API_VERSION` | host version, or `0.0.0` | OpenAPI version. Restart required. |
| `SM_API_DESCRIPTION` | `""` | OpenAPI description. Restart required. |
| `SM_OPENAPI_PUBLIC` | `false` | Expose `/api/openapi.json` anonymously outside development. Restart required. |

### CORS

These apply to the host's `/api/` policy and take effect live after a settings save. See [CORS](/framework/cors) for module policies and precedence.

| Variable | Default | Notes |
|---|---|---|
| `SM_CORS_ALLOW_ORIGINS` | `[]` | JSON array of allowed origins. Empty leaves the host API policy disabled. A wildcard requires credentials to be disabled. |
| `SM_CORS_ALLOW_CREDENTIALS` | `true` | Permit credentialed requests. |
| `SM_CORS_ALLOW_METHODS` | `["GET","POST","PUT","PATCH","DELETE"]` | JSON array of allowed methods. |
| `SM_CORS_ALLOW_HEADERS` | `["Authorization","Content-Type","X-CSRF-Token"]` | JSON array of allowed request headers. |
| `SM_CORS_EXPOSE_HEADERS` | `[]` | JSON array of response headers available to browser scripts. |
| `SM_CORS_MAX_AGE` | `600` | Preflight cache time in seconds. |

## DB connection pool

| Variable | Default | Notes |
|---|---|---|
| `SM_DB_POOL_SIZE` | `10` | SQLAlchemy pool size per process. |
| `SM_DB_MAX_OVERFLOW` | `20` | Extra connections per process beyond the pool size. |
| `SM_DB_POOL_PRE_PING` | `true` | Test connections before use. |
| `SM_DB_POOL_RECYCLE` | `1800` | Connection recycling interval in seconds. |
| `SM_DB_POOL_TIMEOUT` | `30` | Seconds waiting for a pooled connection. |
| `SM_DB_CONNECT_TIMEOUT` | `10` | Driver connection timeout in seconds. |
| `SM_DB_STATEMENT_TIMEOUT_MS` | `0` | PostgreSQL statement timeout. Zero omits the startup parameter. |
| `SM_DB_IDLE_IN_TX_TIMEOUT_MS` | `0` | PostgreSQL idle-in-transaction timeout. Zero omits the startup parameter. |

Total possible web connections are
`workers × (SM_DB_POOL_SIZE + SM_DB_MAX_OVERFLOW)`. See
[database tuning](../database/tuning.md) for worker pools and PgBouncer.

## Sentry (optional)

Install `simple_module_hosting[sentry]`. These settings are read at startup
before the DB opens. See [Sentry](/framework/sentry).

| Variable | Default | Notes |
|---|---|---|
| `SM_SENTRY_DSN` | unset | Enables error reporting in the web and Celery worker processes. |
| `SM_SENTRY_ENVIRONMENT` | `SM_ENVIRONMENT` | Sentry environment tag. |
| `SM_SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Performance trace sampling, from `0.0` to `1.0`. |

## Users module

Edit signup, OAuth/OIDC sign-in and other Users configuration in the admin
settings editor. The variables below seed accounts or supply signing secrets.

| Variable | Default | Notes |
|---|---|---|
| `SM_USERS_BOOTSTRAP_EMAIL` | unset | Creates the first admin if the users table is empty. |
| `SM_USERS_BOOTSTRAP_PASSWORD` | unset | Password paired with the admin email. |
| `SM_USERS_BOOTSTRAP_PASSWORD_GENERATED` | unset | Internal entrypoint marker. `1` logs generated credentials when the bootstrap admin is created. |
| `SM_USERS_BOOTSTRAP_USER_EMAIL` | unset | Optionally seeds a second account without admin privileges. |
| `SM_USERS_BOOTSTRAP_USER_PASSWORD` | unset | Password paired with the second account's email. |
| `SM_USERS_RESET_PASSWORD_TOKEN_SECRET` | dev placeholder | HMAC key for password-reset tokens. Supply a non-placeholder value in production. |
| `SM_USERS_VERIFICATION_TOKEN_SECRET` | dev placeholder | HMAC key for email-verification tokens. Supply a non-placeholder value in production. |

The Users setting `oauth_microsoft_discovery_url` is honored only when
`SM_ENVIRONMENT` is explicitly `development` or `testing`.

## Keycloak and OIDC modules

These variables seed defaults when each module's settings class is imported.
Stored settings take precedence. See [Keycloak](/modules/keycloak) and
[OIDC](/modules/oidc).

| Variable | Default | Notes |
|---|---|---|
| `SM_KEYCLOAK_SERVER_URL` | `""` | Keycloak server base URL. |
| `SM_KEYCLOAK_REALM` | `""` | Realm name. |
| `SM_KEYCLOAK_CLIENT_ID` | `""` | OAuth client ID. |
| `SM_KEYCLOAK_CLIENT_SECRET` | `""` | OAuth client secret. |
| `SM_KEYCLOAK_TRUST_TENANT_CLAIM` | `false` | Allow a verified token's tenant claim to supply tenant context. |
| `SM_OIDC_PROVIDER` | `generic` | Provider preset used for discovery and claims defaults. |
| `SM_OIDC_DISCOVERY_URL` | `""` | OpenID Connect discovery document URL. An explicit URL wins over the preset-derived URL. |
| `SM_OIDC_TENANT_ID` | `""` | Identity provider tenant ID used by presets such as Entra to derive discovery. |
| `SM_OIDC_CLIENT_ID` | `""` | OIDC client ID. |
| `SM_OIDC_CLIENT_SECRET` | `""` | OIDC client secret. |
| `SM_OIDC_ROLES_CLAIM_PATH` | provider preset | Claim path used to extract roles. |

## Background tasks (Celery)

The settings fields below resolve **env → DB → default**. Prefer
`SM_REDIS_URL` for Redis connectivity (generated app, worker and beat files
use only this connection variable) and the BackgroundTasks admin editor
for tuning. Restart affected web, worker and beat processes for changes to
their startup configuration. See [Background tasks](/modules/background_tasks).

### Connection, routing and worker settings

| Variable | Default | Notes |
|---|---|---|
| `SM_BG_TASKS_BROKER_URL` | `redis://localhost:6379/0` | Per-field override for non-Redis transports or separate connections; takes precedence over `SM_REDIS_URL`. Production rejects a localhost broker. |
| `SM_BG_TASKS_RESULT_BACKEND` | `redis://localhost:6379/1` | Per-field override for non-Redis backends or separate connections; takes precedence over `SM_REDIS_URL`. Production rejects a localhost result backend. |
| `SM_BG_TASKS_TASK_DEFAULT_QUEUE` | `default` | Queue for tasks without an explicit route. |
| `SM_BG_TASKS_TASK_ROUTES_OVERRIDE` | `{}` | JSON object mapping task patterns to queues or supported route options. |
| `SM_BG_TASKS_VISIBILITY_TIMEOUT_SECONDS` | unset | Override the Redis visibility timeout. |
| `SM_BG_TASKS_WORKER_MAX_TASKS_PER_CHILD` | unset | Recycle a child after this many tasks. |
| `SM_BG_TASKS_WORKER_MAX_MEMORY_PER_CHILD_KB` | unset | Child memory threshold for recycling, in KiB. |
| `SM_BG_TASKS_TASK_REJECT_ON_WORKER_LOST` | unset | Requeue tasks when the executing worker child is lost. |
| `SM_BG_TASKS_TASK_SOFT_TIME_LIMIT` | unset | Soft task limit in seconds. |
| `SM_BG_TASKS_TASK_TIME_LIMIT` | unset | Hard task limit in seconds. Must exceed the soft limit when both are set. |
| `SM_BG_TASKS_WORKER_CONCURRENCY` | unset | Override worker concurrency. |
| `SM_BG_TASKS_TASK_ALWAYS_EAGER` | `false` | Execute tasks synchronously in the calling process. |
| `SM_BG_TASKS_TASK_EAGER_PROPAGATES` | `true` | Reraise task exceptions in eager mode. |
| `SM_BG_TASKS_BROADCAST_INVALIDATIONS` | `true` | Broadcast cache invalidations across processes when the broker uses Redis. |
| `SM_BG_TASKS_INVALIDATION_CHANNEL` | `simple_module.invalidation` | Redis Pub/Sub channel for invalidation messages. |
| `SM_BG_TASKS_DB_POOL_SIZE` | `2` | Pool size for each worker engine. |
| `SM_BG_TASKS_DB_MAX_OVERFLOW` | `3` | Overflow connections per worker engine. |
| `SM_BG_TASKS_DB_RECYCLE` | `1800` | Worker connection recycling interval in seconds. |
| `SM_BG_TASKS_DB_STATEMENT_TIMEOUT_MS` | unset | Override the host PostgreSQL statement timeout for workers. Zero omits it. |

The per-field broker and result backend variables remain supported for other
transports. They log a deprecation warning when set to Redis URLs.

### Tracking, retained logs and durable events

| Variable | Default | Notes |
|---|---|---|
| `SM_BG_TASKS_STUCK_AFTER_SECONDS` | `300` | Mark running tasks stuck after this long without a heartbeat. |
| `SM_BG_TASKS_STUCK_SWEEP_INTERVAL_SECONDS` | `60` | Interval between stuck-task sweeps. |
| `SM_BG_TASKS_PURGE_INTERVAL_SECONDS` | `86400` | Interval between retention sweeps. |
| `SM_BG_TASKS_RETENTION_DAYS` | `14` | Days to keep terminal task execution records. |
| `SM_BG_TASKS_LOG_SINK_ENABLED` | `false` | Persist application and task log lines in the database. |
| `SM_BG_TASKS_LOG_SINK_LEVEL` | `INFO` | Minimum level for retained logs. |
| `SM_BG_TASKS_LOG_RETENTION_DAYS` | `7` | Days to keep retained logs. |
| `SM_BG_TASKS_OUTBOX_MODE` | `celery` | Durable delivery runner, either `celery` or `inprocess`. |
| `SM_BG_TASKS_OUTBOX_MAX_ATTEMPTS` | `8` | Delivery attempts before an outbox row is marked dead. |
| `SM_BG_TASKS_OUTBOX_SWEEP_INTERVAL_SECONDS` | `5` | Interval between outbox polls. |
| `SM_BG_TASKS_OUTBOX_LEASE_SECONDS` | `300` | How long a worker owns its claimed delivery before another can reclaim it. |
| `SM_BG_TASKS_OUTBOX_HANDLER_TIMEOUT_SECONDS` | unset | Handler deadline per attempt. Unset uses the lease duration minus a safety margin. |

Execution tracking mode and publish tracking are configured in the admin editor.

### Per-process environment settings

| Variable | Default | Notes |
|---|---|---|
| `SM_BG_TASKS_CELERY_OVERRIDES` | `{}` | JSON object of supported raw Celery configuration overrides. Serializer, import and code-loading keys are rejected. |
| `SM_BG_TASKS_WORKER_QUEUES` | unset | Comma-separated queues for this worker. Also scopes the modules it loads. |
| `SM_BG_TASKS_INCLUDE_MODULES` | unset | Comma-separated Python package names to include even without a queue match. |
| `SM_BG_TASKS_EXCLUDE_MODULES` | unset | Comma-separated Python package names to exclude. Exclusion takes precedence over inclusion. |

## File storage module

File storage settings are DB-backed. Edit them under Files in the admin
settings editor. The defaults use the filesystem backend and `./uploads`.
See [File storage](/modules/file_storage) for S3 and custom backends.

## Patterns

### Formats and precedence

Use JSON for Pydantic list and object settings. The trusted proxy and
per-worker queue and module filters explicitly use comma-separated strings.
Pydantic booleans are case-insensitive and accept `true`, `1`, `yes` or
`on` for true and `false`, `0`, `no` or `off` for false. Unrecognized
values fail validation.

For env-readable host settings, process variables take precedence over the
project `.env`, then stored overrides, then defaults. Module settings that
use `DbBackedSettings` resolve from stored values and defaults. The
`smpy settings import-from-env` migration command can import legacy
`SM_<MODULE>_<FIELD>` values into the DB.

### Repository tools and tests

| Variable | Default | Notes |
|---|---|---|
| `SM_APP_PORT` | `8000` | Published host port for the repository Docker run targets. |
| `SM_TEST_DATABASE_URL` | in-memory SQLite; local PostgreSQL `sm_test` for `make test-py-pg` | Database used by the pytest fixtures and the Postgres Make target. |
| `SM_MIGRATIONS_PG_URL` | local PostgreSQL `sm_migrations_check` | Disposable database used by `make migrations-roundtrip-pg`. |
| `SM_TEST_REDIS_URL` | unset | External Redis URL for tests that need Redis. |
| `SM_TEST_REAL_PASSWORD_HASHING` | unset | Any nonempty value keeps real password hashing costs in tests. |
| `SM_TEST_SEPARATE_COMPILE_CACHES` | unset | Any nonempty value disables sharing of compiled SQL between in-memory SQLite test engines. |
| `SM_LOADTEST_COOKIE` | unset | Session cookie supplied to the Locust load test. |

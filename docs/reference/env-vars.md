# Environment variables

All env vars use the `SM_` prefix. Settings are loaded at boot — anything that must be **known before the DB is open** lives here. Runtime-tunable settings (SMTP creds, feature flags, storage backends) live in the DB-backed settings store and are edited from `/admin/settings/`.

This is the full reference. See [Configuration](/guide/configuration) for a narrative overview.

## Framework

| Variable | Default | Notes |
|---|---|---|
| `SM_DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | **Required in production.** Async URL: `postgresql+asyncpg://user:pw@host:5432/db` or `sqlite+aiosqlite:///./app.db`. Relative sqlite paths resolve against the project root (the `.env` location), not the process cwd — CLI tools run from `host/` hit the same file as the app. |
| `SM_ENVIRONMENT` | `development` | `development` and `testing` are the only non-prod values (placeholder-secret check is skipped for both). Any value other than `development` triggers strict module discovery. |
| `SM_SECRET_KEY` | `change-me-in-production` | **Must** be overridden in production — session cookie signing key. |
| `SM_DEBUG` | `false` | Enables debug mode (tracebacks in HTTP responses). |
| `SM_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`. |
| `SM_LOG_FORMAT` | `json` | `text` for readable dev logs, `json` for structured logs in prod. |
| `SM_MODULES_ENABLED` | unset | Comma-separated allow-list to disable modules without uninstalling them. |
| `SM_VITE_DEV_URL` | `http://localhost:5050` | Dev only — where the Vite HMR client connects. Freshly scaffolded apps also derive the Vite dev server's port and origin from this one value (via `client_app/vite.dev-url.ts`), so changing it here is the whole move. |
| `SM_VITE_PORT` | `5050` | Dev only — port this repo's own host `vite.config.ts` binds to. If you change it, set `SM_VITE_DEV_URL` to match so the backend points the HMR client at the right origin. New scaffolds don't need it — they read `SM_VITE_DEV_URL` directly. |
| `SM_PROJECT_ROOT` | unset | Overrides project-root discovery: where the `.env` is looked up and what relative sqlite paths resolve against. Normally unnecessary — settings walk up from the cwd (stopping at repo boundaries and `$HOME`) to find the `.env` on their own. |
| `SM_AUTH_PUBLIC_PATHS` | `[]` | JSON array of host-level anonymous-access path prefixes. Escape hatch for exposing a route without a session when no module owns it; modules should prefer the method-aware `register_public_routes` hook. |
| `SM_TRUSTED_PROXY` | unset | Comma-separated proxy IPs / CIDRs whose `X-Forwarded-*` headers are trusted, or `*` to trust any peer (correct when the container is only reachable through one proxy). Setting it installs uvicorn's `ProxyHeadersMiddleware` outermost, so request logs record the real client IP and `request.url.scheme` reflects `X-Forwarded-Proto`. **Recommended behind a TLS-terminating proxy**, where otherwise every request is attributed to the proxy's own address — in the audit log as much as in the logs. It is no longer needed for Inertia: the page url is root-relative, so `pushState` can't see a cross-scheme url whatever the proxy sends (it used to throw a `SecurityError` on every page — GH #223). It is still needed for anything that builds an absolute url from `request.url.scheme`/`request.url_for(...)` — notably OAuth/OIDC's callback url and the locale cookie's `secure` flag — left unset behind such a proxy, an OAuth `redirect_uri` ships as `http://…` and most providers reject it. Forwarded headers are never trusted by default. |

## DB connection pool

| Variable | Default | Notes |
|---|---|---|
| `SM_DB_POOL_SIZE` | `10` | SQLAlchemy `pool_size` (per process). |
| `SM_DB_MAX_OVERFLOW` | `20` | SQLAlchemy `max_overflow` (per process). |
| `SM_DB_POOL_PRE_PING` | `true` | Test connections before use. |
| `SM_DB_POOL_RECYCLE` | `1800` | Recycle connections after N seconds (helps with LB idle drops). |

Pools are **per process**. With multiple `uvicorn --workers`, total connections =
`workers × (SM_DB_POOL_SIZE + SM_DB_MAX_OVERFLOW)`; keep it under the database's
`max_connections` (Postgres default 100) or workers raise
`asyncpg.TooManyConnectionsError` under load. See
[deployment](deployment.md#build) for sizing examples.

## Host settings (`HostSettings`)

These are declared on `HostSettings` and registered under `package="host"`, so they appear in the admin UI at `/admin/settings/`. They are **also** readable from env: `Settings` combines `HostSettings` with `BootstrapSettings` and inherits its `env_prefix="SM_"`, so each field below resolves from the matching `SM_*` variable at boot.

Which source actually wins depends on the field, because `HostSettings` is consumed through two different objects:

| Setting | Env var | Default | Read from | Notes |
|---|---|---|---|---|
| `multi_tenant` | `SM_MULTI_TENANT` | `false` | **env at boot** | Decides whether `TenantMiddleware` is installed. A DB write cannot install a middleware after boot. |
| `tenant_header` | `SM_TENANT_HEADER` | `""` | **env at boot** | Header identifying the tenant (empty = header lookup disabled). |
| `i18n_default_locale` | `SM_I18N_DEFAULT_LOCALE` | `en` | **env at boot** | Must be in `i18n_supported_locales`. |
| `i18n_supported_locales` | `SM_I18N_SUPPORTED_LOCALES` | `["en"]` | **env at boot** | JSON array, e.g. `["en","es"]`. |
| `i18n_cookie_name` | `SM_I18N_COOKIE_NAME` | `locale` | **env at boot** | Cookie storing the selected locale. |
| `maintenance_mode` | *(none — see below)* | `false` | **DB at request time** | Serve everyone but admins a 503. DB-backed so flipping it needs no redeploy — see [Deployment](/reference/deployment#maintenance-mode). |
| `maintenance_message` | *(none — see below)* | `""` | **DB at request time** | Optional operator note on the maintenance page. |

The split is not arbitrary. The boot instance (`Settings()`, env-derived) lands on `app.state.sm.settings` and is what configures middleware at construction — `LocaleMiddleware` captures its locale set there, and the tenancy flag decides whether `TenantMiddleware` is added at all. The DB-hydrated instance is a plain `HostSettings` on `app.state.host.settings`, which declares no `env_prefix` and so is defaults-plus-overrides; `MaintenanceMiddleware` reads that one on every request.

So editing the tenancy or i18n rows in the admin UI updates what the UI shows without moving what the app serves — those need the env var and a restart. Maintenance mode is the one that genuinely takes effect live.

The two maintenance fields have **no working env var**, and this is worth stating plainly because the shape of the code suggests otherwise. `SM_MAINTENANCE_MODE=true` does set `maintenance_mode` on the boot `Settings()` object — but nothing reads maintenance from there, and the DB-hydrated `HostSettings` that `MaintenanceMiddleware` does read carries no `SM_` prefix, so it never sees the variable. Setting it looks plausible and silently does nothing. Flip the flag in the admin UI, or write the settings row directly.

## Users module

Most users settings (signup, mailer, SMTP, OAuth/OIDC credentials, rate limits) are now **DB-backed** — edit them in the admin UI at `/admin/settings/` under Users, not via env vars. The env vars below are the genuine bootstrap-time exceptions read at process start.

| Variable | Default | Notes |
|---|---|---|
| `SM_USERS_BOOTSTRAP_EMAIL` | unset | Auto-creates an admin if set **and** the users table is empty. |
| `SM_USERS_BOOTSTRAP_PASSWORD` | unset | Paired with the email above. |
| `SM_USERS_BOOTSTRAP_USER_EMAIL` | unset | Optional second non-admin seed user (handy in dev). |
| `SM_USERS_BOOTSTRAP_USER_PASSWORD` | unset | Paired with the user email above. |
| `SM_USERS_RESET_PASSWORD_TOKEN_SECRET` | dev placeholder | HMAC key for password-reset tokens. **Must** be overridden in production (boot fails otherwise). |
| `SM_USERS_VERIFICATION_TOKEN_SECRET` | dev placeholder | HMAC key for email-verification tokens. **Must** be overridden in production (boot fails otherwise). |

## Background tasks (Celery)

Celery config (`broker_url`, `result_backend`, queue, retention, etc.) is now **DB-backed** — edit it in the admin UI at `/admin/settings/` under BackgroundTasks. Defaults are `redis://localhost:6379/0` (broker) and `/1` (result backend). Because workers read the broker/backend once at process start, changing those values requires a worker restart.

Three fields are still read from the environment, because they have to work *before* any DB row exists. A stored DB value still wins once hydration runs.

| Variable | Default | Notes |
|---|---|---|
| `SM_BG_TASKS_BROKER_URL` | `redis://localhost:6379/0` | Read at construction. Needed in a container: the production validator rejects a `localhost` broker, so without this an app with the module installed can't boot far enough to hydrate settings — and a worker process, which never sees `app.state`, has no other source at all. |
| `SM_BG_TASKS_RESULT_BACKEND` | `redis://localhost:6379/1` | Same reasoning as the broker. |
| `SM_BG_TASKS_TASK_ALWAYS_EAGER` | `false` | Read at module-import time, so test suites that never run the FastAPI lifespan can still flip it. Runs tasks synchronously in the calling process. |

## File storage module

File storage config is now **DB-backed** — edit it in the admin UI at `/admin/settings/` under Files. The key fields and defaults:

| Setting | Default | Notes |
|---|---|---|
| `backend` | `filesystem` | `filesystem` or `s3` (S3-compatible: AWS S3, MinIO, R2). |
| `fs_root_path` | `./uploads` | Filesystem backend root directory. |
| `s3_bucket` | `""` | S3 bucket name (required when backend is `s3`). |
| `s3_region` | `""` | S3 region (required when backend is `s3`). |
| `s3_endpoint_url` | `""` | Custom endpoint for MinIO / R2; blank uses AWS default. |

## Patterns

### Per-module prefix

Every module-owned env var uses `SM_<MODULE_UPPER>_*`. Keeps settings self-describing and avoids collisions.

### Comma-separated lists

Pydantic parses comma-separated strings into `list[str]` — `SM_MODULES_ENABLED=users,dashboard` becomes `["users", "dashboard"]`. (`SM_AUTH_PUBLIC_PATHS` is the exception — it takes a JSON array, e.g. `["/status", "/api/webhook"]`.)

### Booleans

`true`, `1`, `yes`, `on` → `True`. Everything else → `False`. Pydantic is strict — `SM_DEBUG=True` works, `SM_DEBUG=TRUE` works, but watch for whitespace.

### Placeholder-secret check

In production (`SM_ENVIRONMENT` not in `{development, testing}`), boot fails if `SM_SECRET_KEY == "change-me-in-production"`. Override before deploying.

### `.env` files

The app loads `.env` via pydantic's `BaseSettings`. Order of precedence:

1. Actual environment variables.
2. `.env` file in the current working directory.
3. Defaults from the `Settings` class.

Keep secrets out of `.env.example` — check in only non-secret defaults.

### Module-enabled allow-list

```bash
SM_MODULES_ENABLED=users,orders,dashboard
```

Loads only the listed modules. Useful for:

- **Tests** — `SM_MODULES_ENABLED=users,orders` for a minimal app.
- **Worker processes** — if you run a Celery worker as a separate container, it only needs `background_tasks` and whatever modules define tasks it processes.
- **Emergency disable** — hide a broken module without rebuilding the image. Remove it from the list, restart.

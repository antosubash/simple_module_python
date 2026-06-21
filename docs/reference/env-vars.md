# Environment variables

All env vars use the `SM_` prefix. Settings are loaded at boot — anything that must be **known before the DB is open** lives here. Runtime-tunable settings (SMTP creds, feature flags, storage backends) live in the DB-backed settings store and are edited from `/settings/modules`.

This is the full reference. See [Configuration](/guide/configuration) for a narrative overview.

## Framework

| Variable | Default | Notes |
|---|---|---|
| `SM_DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | **Required in production.** Async URL: `postgresql+asyncpg://user:pw@host:5432/db` or `sqlite+aiosqlite:///./app.db`. |
| `SM_ENVIRONMENT` | `development` | `development` and `testing` are the only non-prod values (placeholder-secret check is skipped for both). Any value other than `development` triggers strict module discovery. |
| `SM_SECRET_KEY` | `change-me-in-production` | **Must** be overridden in production — session cookie signing key. |
| `SM_DEBUG` | `false` | Enables debug mode (tracebacks in HTTP responses). |
| `SM_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`. |
| `SM_LOG_FORMAT` | `json` | `text` for readable dev logs, `json` for structured logs in prod. |
| `SM_MODULES_ENABLED` | unset | Comma-separated allow-list to disable modules without uninstalling them. |
| `SM_VITE_DEV_URL` | `http://localhost:5050` | Dev only — where the Vite HMR client connects. |
| `SM_AUTH_PUBLIC_PATHS` | `[]` | JSON array of host-level anonymous-access path prefixes. Escape hatch for exposing a route without a session when no module owns it; modules should prefer the method-aware `register_public_routes` hook. |

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

## Host settings (DB-backed, not env)

Multi-tenancy and i18n configuration live in the DB-backed host settings store (`HostSettings`, registered under `package="host"`), **not** in env vars. Edit them in the admin UI at `/settings/modules` under the host section. Their defaults:

| Setting | Default | Notes |
|---|---|---|
| `multi_tenant` | `false` | Enables `TenantMiddleware` + `MultiTenantMixin` auto-filter. |
| `tenant_header` | `""` | HTTP header that identifies the current tenant (empty = tenant middleware disabled). |
| `i18n_default_locale` | `en` | Must be in `i18n_supported_locales`. |
| `i18n_supported_locales` | `["en"]` | e.g. `["en", "es", "de"]`. |
| `i18n_cookie_name` | `locale` | Cookie that stores the user's selected locale. |

## Users module

Most users settings (signup, mailer, SMTP, OAuth/OIDC credentials, rate limits) are now **DB-backed** — edit them in the admin UI at `/settings/modules` under Users, not via env vars. The env vars below are the genuine bootstrap-time exceptions read at process start.

| Variable | Default | Notes |
|---|---|---|
| `SM_USERS_BOOTSTRAP_EMAIL` | unset | Auto-creates an admin if set **and** the users table is empty. |
| `SM_USERS_BOOTSTRAP_PASSWORD` | unset | Paired with the email above. |
| `SM_USERS_BOOTSTRAP_USER_EMAIL` | unset | Optional second non-admin seed user (handy in dev). |
| `SM_USERS_BOOTSTRAP_USER_PASSWORD` | unset | Paired with the user email above. |
| `SM_USERS_RESET_PASSWORD_TOKEN_SECRET` | dev placeholder | HMAC key for password-reset tokens. **Must** be overridden in production (boot fails otherwise). |
| `SM_USERS_VERIFICATION_TOKEN_SECRET` | dev placeholder | HMAC key for email-verification tokens. **Must** be overridden in production (boot fails otherwise). |

## Background tasks (Celery)

Celery config (`broker_url`, `result_backend`, queue, retention, etc.) is now **DB-backed** — edit it in the admin UI at `/settings/modules` under BackgroundTasks. Defaults are `redis://localhost:6379/0` (broker) and `/1` (result backend). Because workers read the broker/backend once at process start, changing those values requires a worker restart.

The one field still read from the environment at import time:

| Variable | Default | Notes |
|---|---|---|
| `SM_BG_TASKS_TASK_ALWAYS_EAGER` | `false` | Run tasks synchronously in the calling process (used by tests). |

## File storage module

File storage config is now **DB-backed** — edit it in the admin UI at `/settings/modules` under Files. The key fields and defaults:

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

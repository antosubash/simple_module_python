# Environment variables

All env vars use the `SM_` prefix. Settings are loaded at boot — anything that must be **known before the DB is open** lives here. Runtime-tunable settings (SMTP creds, feature flags, storage backends) live in the DB-backed settings store and are edited from `/settings/modules`.

This is the full reference. See [Configuration](/guide/configuration) for a narrative overview.

## Framework

| Variable | Default | Notes |
|---|---|---|
| `SM_DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | **Required in production.** Async URL: `postgresql+asyncpg://user:pw@host:5432/db` or `sqlite+aiosqlite:///./app.db`. |
| `SM_ENVIRONMENT` | `development` | Any value other than `development`, `test`, `testing` triggers strict discovery + placeholder-secret checks. |
| `SM_SECRET_KEY` | `change-me-in-production` | **Must** be overridden in production — session cookie signing key. |
| `SM_DEBUG` | `false` | Enables debug mode (tracebacks in HTTP responses). |
| `SM_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`. |
| `SM_LOG_FORMAT` | `plain` | `plain` for dev, `json` for structured logs in prod. |
| `SM_MULTI_TENANT` | `false` | Enables `TenantMiddleware` + `MultiTenantMixin` auto-filter. |
| `SM_TENANT_HEADER` | `X-Tenant-ID` | HTTP header that identifies the current tenant. |
| `SM_MODULES_ENABLED` | unset | Comma-separated allow-list to disable modules without uninstalling them. |
| `SM_VITE_DEV_URL` | `http://localhost:5050` | Dev only — where the Vite HMR client connects. |

## DB connection pool

| Variable | Default | Notes |
|---|---|---|
| `SM_DB_POOL_SIZE` | `5` | SQLAlchemy `pool_size`. |
| `SM_DB_MAX_OVERFLOW` | `10` | SQLAlchemy `max_overflow`. |
| `SM_DB_POOL_PRE_PING` | `true` | Test connections before use. |
| `SM_DB_POOL_RECYCLE` | `1800` | Recycle connections after N seconds (helps with LB idle drops). |

## Internationalization

| Variable | Default | Notes |
|---|---|---|
| `SM_I18N_DEFAULT_LOCALE` | `en` | Must be in `SM_I18N_SUPPORTED_LOCALES`. |
| `SM_I18N_SUPPORTED_LOCALES` | `en` | Comma-separated, e.g. `en,es,de`. |
| `SM_I18N_COOKIE_NAME` | `locale` | Cookie that stores the user's selected locale. |

## Users module

| Variable | Default | Notes |
|---|---|---|
| `SM_USERS_BOOTSTRAP_EMAIL` | unset | Auto-creates an admin if set **and** `users_user` is empty. |
| `SM_USERS_BOOTSTRAP_PASSWORD` | unset | Paired with the email above. |
| `SM_USERS_ALLOW_SIGNUP` | `false` | If `true`, `/users/register` is public. |
| `SM_USERS_MAILER` | `console` | `console` logs the invite link to stdout; `smtp` sends real emails. |
| `SM_USERS_BASE_URL` | derived | Public URL used to build invite links. |
| `SM_USERS_SMTP_HOST` | — | Required when mailer is `smtp`. |
| `SM_USERS_SMTP_PORT` | `587` | |
| `SM_USERS_SMTP_USERNAME` | — | |
| `SM_USERS_SMTP_PASSWORD` | — | |
| `SM_USERS_SMTP_FROM` | — | |
| `SM_USERS_SMTP_TLS` | `true` | |

## Background tasks (Celery)

Prefix `SM_BG_TASKS_*`. Set in `docker-compose.yml` for local dev.

| Variable | Default | Notes |
|---|---|---|
| `SM_BG_TASKS_BROKER_URL` | `redis://localhost:6379/0` | Celery broker. |
| `SM_BG_TASKS_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery result backend. |

## File storage module

| Variable | Default | Notes |
|---|---|---|
| `SM_FILE_STORAGE_BACKEND` | `local` | `local`, `s3`, or `memory`. |
| `SM_FILE_STORAGE_LOCAL_ROOT` | `./storage` | Local backend root directory. |
| `SM_FILE_STORAGE_S3_BUCKET` | — | S3 bucket name. |
| `SM_FILE_STORAGE_S3_REGION` | — | S3 region. |

Most of the storage config moved to DB-backed settings; the env vars above are the ones needed at bootstrap.

## Patterns

### Per-module prefix

Every module-owned env var uses `SM_<MODULE_UPPER>_*`. Keeps settings self-describing and avoids collisions.

### Comma-separated lists

Pydantic parses comma-separated strings into `list[str]` — `SM_I18N_SUPPORTED_LOCALES=en,es,de` becomes `["en", "es", "de"]`.

### Booleans

`true`, `1`, `yes`, `on` → `True`. Everything else → `False`. Pydantic is strict — `SM_DEBUG=True` works, `SM_DEBUG=TRUE` works, but watch for whitespace.

### Placeholder-secret check

In production (`SM_ENVIRONMENT != development`), boot fails if `SM_SECRET_KEY == "change-me-in-production"`. Override before deploying.

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

# Configuration

Runtime configuration has **two** sources, in order of precedence:

1. **Environment variables** (`SM_*`) — read at boot, before the DB connection is open. Use for bootstrap plumbing (DB URL, secret key, feature-flag overrides for tests).
2. **DB-backed settings** — edited from `/settings/modules` at runtime. Use for everything else: SMTP creds, storage backends, module-specific toggles.

Most deployments only need `SM_DATABASE_URL` and `SM_SECRET_KEY` in the environment — everything else is configurable from the admin UI.

## Framework env vars

Prefix is always `SM_`. These are parsed by `simple_module_hosting.settings.Settings` (pydantic) at startup.

| Variable | Default | Notes |
|---|---|---|
| `SM_DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | **Required in production.** Async URL. Postgres: `postgresql+asyncpg://…` |
| `SM_ENVIRONMENT` | `development` | Any value other than `development`, `test`, `testing` triggers strict discovery + placeholder-secret checks. |
| `SM_SECRET_KEY` | `change-me-in-production` | **Must** be overridden in production — session cookie signing key. |
| `SM_VITE_DEV_URL` | `http://localhost:5050` | Dev only — where the Vite HMR client connects. |
| `SM_DEBUG` | `false` | Enables debug mode (shows tracebacks in HTTP responses). |
| `SM_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `SM_LOG_FORMAT` | `plain` | `plain` for dev, `json` for structured logs in prod. |
| `SM_MULTI_TENANT` | `false` | Enables `TenantMiddleware` + `MultiTenantMixin` auto-filter. |
| `SM_TENANT_HEADER` | `X-Tenant-ID` | HTTP header that identifies the current tenant. |
| `SM_MODULES_ENABLED` | unset (all enabled) | Comma-separated allow-list to disable modules without uninstalling them. |

## Database bootstrap knobs

Only change if you know what you're doing — these must be set *before* the DB connection opens, so they can't live in the DB-backed settings store.

| Variable | Default | Notes |
|---|---|---|
| `SM_DB_POOL_SIZE` | `5` | SQLAlchemy `pool_size` |
| `SM_DB_MAX_OVERFLOW` | `10` | SQLAlchemy `max_overflow` |
| `SM_DB_POOL_PRE_PING` | `true` | Test connections before use |
| `SM_DB_POOL_RECYCLE` | `1800` | Recycle connections after N seconds |

## Internationalization

| Variable | Default | Notes |
|---|---|---|
| `SM_I18N_DEFAULT_LOCALE` | `en` | Must be in `SM_I18N_SUPPORTED_LOCALES`. |
| `SM_I18N_SUPPORTED_LOCALES` | `en` | Comma-separated, e.g. `en,es,de`. |
| `SM_I18N_COOKIE_NAME` | `locale` | Cookie that stores the user's selected locale. |

## Users module

Prefix `SM_USERS_*`. These live in the env for bootstrap; everything else moved to the DB-backed settings store.

| Variable | Default | Notes |
|---|---|---|
| `SM_USERS_BOOTSTRAP_EMAIL` | unset | Auto-creates an admin if set **and** `users_user` is empty. |
| `SM_USERS_BOOTSTRAP_PASSWORD` | unset | Paired with the email above. |
| `SM_USERS_ALLOW_SIGNUP` | `false` | If `true`, `/users/register` is public. |
| `SM_USERS_MAILER` | `console` | `console` (logs invite link to stdout) or `smtp`. |
| `SM_USERS_BASE_URL` | derived | The public URL used to build invite links. |
| `SM_USERS_SMTP_HOST` | — | Only when `SM_USERS_MAILER=smtp`. |
| `SM_USERS_SMTP_PORT` | `587` | |
| `SM_USERS_SMTP_USERNAME` | — | |
| `SM_USERS_SMTP_PASSWORD` | — | |
| `SM_USERS_SMTP_FROM` | — | |
| `SM_USERS_SMTP_TLS` | `true` | |

## Background tasks (Celery)

Prefix `SM_BG_TASKS_*`. The defaults in `docker-compose.yml` already set these so Celery can reach the in-container `redis` service before DB-backed settings are loaded.

| Variable | Default | Notes |
|---|---|---|
| `SM_BG_TASKS_BROKER_URL` | `redis://localhost:6379/0` | Celery broker. |
| `SM_BG_TASKS_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery result backend. |

## DB-backed settings

After upgrading from an older deployment, import existing `SM_*` values into the DB settings store once:

```bash
uv run sm-settings import-from-env
```

This is idempotent — it only seeds keys that don't have a DB override yet.

From then on, edit at `/settings/modules` (requires the `settings.manage` permission). Changes apply immediately; no restart needed.

## Per-module settings convention

When you write your own module, declare settings as a dataclass on `app.state.<module_lower>` inside `register_settings(app)`. The prefix for env vars must be `SM_<MODULE>_*`.

```python
# modules/orders/orders/settings.py
from dataclasses import dataclass
from pydantic_settings import BaseSettings

class OrdersEnv(BaseSettings):
    max_items_per_order: int = 100
    class Config:
        env_prefix = "SM_ORDERS_"

@dataclass
class OrdersState:
    settings: OrdersEnv

# modules/orders/orders/module.py
class OrdersModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        app.state.orders = OrdersState(settings=OrdersEnv())
```

If you override `register_settings` but don't write to `app.state.<module_lower>`, diagnostic `SM012` warns in dev. See [Settings & app.state](/framework/settings) for details.

## Placeholder-secret check

In production (`SM_ENVIRONMENT != development`), boot fails if `SM_SECRET_KEY` is still the default `change-me-in-production`. Override it before deploying.

# Configuration

Runtime configuration has **two** sources, in order of precedence:

1. **Environment variables** (`SM_*`) — read at boot, before the DB connection is open. Use for bootstrap plumbing (DB URL, secret key, feature-flag overrides for tests).
2. **DB-backed settings** — edited from `/settings/modules` at runtime. Use for everything else: SMTP creds, storage backends, module-specific toggles.

Most deployments only need `SM_DATABASE_URL` and `SM_SECRET_KEY` in the environment — everything else is configurable from the admin UI.

## Framework env vars (bootstrap)

Prefix is always `SM_`. These are the pre-DB knobs read by `simple_module_hosting.bootstrap_settings.BootstrapSettings` (pydantic) at startup — they're needed to open the DB, sign cookies, or configure the process, so they can't live in the DB-backed store.

| Variable | Default | Notes |
|---|---|---|
| `SM_DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | **Required in production.** Async URL. Postgres: `postgresql+asyncpg://…` |
| `SM_ENVIRONMENT` | `development` | Any value other than `development`, `test`, `testing` triggers strict discovery + placeholder-secret checks. |
| `SM_SECRET_KEY` | `change-me-in-production` | **Must** be overridden in production — session cookie signing key. |
| `SM_VITE_DEV_URL` | `http://localhost:5050` | Dev only — where the Vite HMR client connects. |
| `SM_DEBUG` | `false` | Enables debug mode (shows tracebacks in HTTP responses). |
| `SM_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `SM_LOG_FORMAT` | `json` | `json` (structured) or `text`. |
| `SM_MODULES_ENABLED` | unset (all enabled) | Comma-separated allow-list to disable modules without uninstalling them. |
| `SM_AUTH_PUBLIC_PATHS` | `[]` | JSON array of anonymous-access path prefixes — a host-level escape hatch. Modules should prefer the `register_public_routes` hook. |

Multi-tenancy (`multi_tenant`, `tenant_header`) and i18n (`i18n_default_locale`, `i18n_supported_locales`, `i18n_cookie_name`) are **DB-backed host settings** now, not env vars — edit them under `host` at `/settings/modules`. (`smpy new --tenancy` still writes `SM_MULTI_TENANT=true` into `.env.example` as a scaffold convenience, and tests can override these.)

## Database bootstrap knobs

Only change if you know what you're doing — these must be set *before* the DB connection opens, so they can't live in the DB-backed settings store.

| Variable | Default | Notes |
|---|---|---|
| `SM_DB_POOL_SIZE` | `10` | SQLAlchemy `pool_size` |
| `SM_DB_MAX_OVERFLOW` | `20` | SQLAlchemy `max_overflow` |
| `SM_DB_POOL_PRE_PING` | `true` | Test connections before use |
| `SM_DB_POOL_RECYCLE` | `1800` | Recycle connections after N seconds |

## Internationalization

These are **DB-backed host settings** (under `host` in `/settings/modules`), not env vars.

| Setting | Default | Notes |
|---|---|---|
| `i18n_default_locale` | `en` | Must be in `i18n_supported_locales`. |
| `i18n_supported_locales` | `["en"]` | List of supported locales, e.g. `["en", "es", "de"]`. |
| `i18n_cookie_name` | `locale` | Cookie that stores the user's selected locale. |

## Users module

Only the first-boot **bootstrap seed** is read from the env (prefix `SM_USERS_*`). Signup policy, mailer, SMTP creds, and base URL all moved to the DB-backed settings store — edit them under `users` at `/settings/modules`.

| Variable | Default | Notes |
|---|---|---|
| `SM_USERS_BOOTSTRAP_EMAIL` | unset | Auto-creates an admin if set **and** `users_user` is empty. |
| `SM_USERS_BOOTSTRAP_PASSWORD` | unset | Paired with the email above. |
| `SM_USERS_BOOTSTRAP_USER_EMAIL` | unset | Optional second, non-admin seed user. |
| `SM_USERS_BOOTSTRAP_USER_PASSWORD` | unset | Paired with the user email above. |

DB-backed users settings (defaults): `allow_signup=false`, `mailer=console` (or `smtp`), `base_url=http://localhost:8000`, and the `smtp_*` fields (`smtp_port=587`, `smtp_from=no-reply@localhost`, `smtp_tls=true`).

## Background tasks (Celery)

The broker/result settings are DB-backed (under `background_tasks` in `/settings/modules`) with the defaults below. The generated `docker-compose.yml` sets `SM_BG_TASKS_BROKER_URL` / `SM_BG_TASKS_RESULT_BACKEND` on the `worker` and `beat` containers so they reach the in-container `redis` service.

| Setting | Default | Notes |
|---|---|---|
| `broker_url` | `redis://localhost:6379/0` | Celery broker. |
| `result_backend` | `redis://localhost:6379/1` | Celery result backend. |

## DB-backed settings

After upgrading from an older deployment, import existing `SM_*` values into the DB settings store once:

```bash
uv run smpy settings import-from-env
```

This is idempotent — it only seeds keys that don't have a DB override yet.

From then on, edit at `/settings/modules` (requires the `settings.manage` permission). Changes apply immediately; no restart needed.

## Per-module settings convention

When you write your own module, declare settings as a `pydantic_settings.BaseSettings` subclass and store them on `app.state.<module_lower>` (the lowercase package name) inside `register_settings(app)`. Env-var prefix is `SM_<MODULE>_*`.

```python
# modules/orders/orders/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class OrdersSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_ORDERS_", extra="ignore")

    max_items_per_order: int = 100

# modules/orders/orders/services.py
from dataclasses import dataclass
from orders.settings import OrdersSettings

@dataclass
class OrdersServices:
    settings: OrdersSettings

# modules/orders/orders/module.py
class OrdersModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        from orders.services import OrdersServices
        from orders.settings import OrdersSettings

        app.state.orders = OrdersServices(settings=OrdersSettings())
```

If you override `register_settings` but don't write to `app.state.<module_lower>`, diagnostic `SM012` warns in dev. See [Settings & app.state](/framework/settings) for details.

## Placeholder-secret check

In production (`SM_ENVIRONMENT != development`), boot fails if `SM_SECRET_KEY` is still the default `change-me-in-production`. Override it before deploying.

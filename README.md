# simple_module_python

A modular-monolith framework for Python. Each feature lives in its own self-contained module — its own SQLAlchemy models, schema, FastAPI endpoints, React pages — but everything ships as one FastAPI + Inertia.js + React app. No microservice tax, no API-client glue; just plugin modules that compose at boot.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy async, Alembic
- **Frontend:** Inertia.js + React + Tailwind CSS 4, Vite HMR
- **Auth:** Keycloak (OIDC, cookie-based sessions)
- **Tooling:** uv workspaces, Ruff, ty, Biome, pytest

## Quickstart

```bash
# 1. Install Python and JS deps
make install

# 2. Copy env template (defaults work for local SQLite dev)
cp .env.example .env

# 3. Start Keycloak + Postgres (skip if sticking with SQLite)
make docker-up

# 4. Run migrations
make migrate

# 5. Start API + Vite dev server in parallel
make dev
```

Hit `http://localhost:8000` — you land on the public page. `/auth/login` takes you through Keycloak, `/dashboard` is the authenticated home, `/products` is a fully-working example module.

## Create a new module

```bash
make new-module name=orders
```

That scaffolds `modules/orders/` with a working CRUD module end-to-end — `ModuleMeta`, SQLAlchemy model with `AuditMixin`, Pydantic contracts, service layer, REST + Inertia view endpoints, `Browse/Create/Edit.tsx` pages, and tests. Next:

```bash
# 1. Edit modules/orders/orders/models.py to your actual schema
# 2. Generate a migration
make migration msg="add orders tables"
# 3. Apply it
make migrate
# 4. Run the scaffolded tests
make test
```

The new module is automatically discovered (via Python entry points), its routes register at `/api/orders` and `/orders`, and its sidebar entry appears in the menu.

## Project layout

```
framework/
  core/        # module system, discovery, events, diagnostics
  db/          # per-module Base, session, mixins, listeners
  hosting/     # app_builder, middleware, settings, Inertia glue
modules/       # plugin modules (auth, dashboard, products, ...)
host/
  main.py      # FastAPI entry point
  routes.py    # host-level routes (landing page)
  client_app/  # Vite + React client app
  migrations/  # Alembic migrations
packages/
  ui/          # shared shadcn/ui components & layouts
scripts/
  new_module.py  # module scaffolder (called by `make new-module`)
docs/
  plans/                      # design + implementation plans
  framework-conventions.md    # invariants for module authors
```

## Common commands

| Command | What it does |
|---|---|
| `make install` | Install Python (`uv sync`) and JS (`npm install`) deps |
| `make dev` | Docker up + API + Vite dev servers in parallel |
| `make test` | Run the pytest suite |
| `make lint` | Ruff + ty + Biome + tsc |
| `make doctor` | Run module diagnostics (orphan pages, missing meta, coupling violations) |
| `make migrate` | Apply pending Alembic migrations |
| `make migration msg="..."` | Autogenerate a new migration |
| `make new-module name=<name>` | Scaffold a new module |
| `make kill` | Stop any running dev servers (ports 8000, 5173) |
| `make docker-up` / `docker-down` | Manage Keycloak + Postgres containers |

## Configuration

All settings are `SM_`-prefixed env vars. Defaults in `.env.example` cover local dev. Key knobs:

| Variable | Default | Notes |
|---|---|---|
| `SM_DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | Async URL. Postgres: `postgresql+asyncpg://...` |
| `SM_ENVIRONMENT` | `development` | Anything else triggers strict module discovery |
| `SM_SECRET_KEY` | _(placeholder)_ | **Must** change in production — signs session cookies |
| `SM_AUTH_KEYCLOAK_URL` | `http://localhost:8080` | Auth module settings (note the `SM_AUTH_` prefix) |
| `SM_MULTI_TENANT` | `false` | Set `true` to enable `TenantMiddleware` |
| `SM_TENANT_HEADER` | `` | Empty = token-only; set e.g. `X-Tenant-ID` to enable header fallback |

See `framework-conventions.md` for the settings-per-module convention.

## Architecture

- **Modules**: discovered via Python entry points at boot. Each module subclasses `ModuleBase` and opts into the lifecycle hooks it needs (`register_routes`, `register_menu_items`, `register_permissions`, `register_middleware`, `on_startup`, ...).
- **Database isolation**: PostgreSQL → one schema per module. SQLite → single schema, `__tablename__` prefixed with the module name.
- **Middleware pipeline** (LIFO order of execution): CorrelationId → RequestLogging → SecurityHeaders → Session → `<module middleware>` → Tenant (opt-in) → Locale → InertiaLayoutData → app.
- **Diagnostics**: `make doctor` runs a static analyzer over installed modules looking for orphan pages, phantom renders, empty modules, framework/plugin coupling, migration drift, and locale-file consistency. Errors fail the boot in production.
- **Internationalization**: per-module `locales/<lang>.json` files merged at boot into `I18nRegistry`. Frontend uses `i18next` with type-safe keys; backend uses `Babel` for CLDR plurals. Locale resolved per request via cookie → `Accept-Language` → `SM_I18N_DEFAULT_LOCALE`. See `docs/framework-conventions.md` → Internationalization.

Deeper dives in `docs/plans/`:

- [Module lifecycle hooks](docs/superpowers/specs/2026-04-13-module-lifecycle-hooks-design.md)
- [Alembic migrations design](docs/plans/2026-04-13-alembic-migrations-design.md)
- [DB state refactor](docs/plans/2026-04-13-eliminate-global-mutable-db-state-design.md)
- [DX hardening (latest)](docs/plans/2026-04-14-dx-hardening-design.md)

## Contributing

- Write tests with the fixtures in `conftest.py` (`db_session`, `authenticated_client`).
- Lint with `make lint` before pushing; CI runs all four checks in parallel.
- Stick to the conventions in `docs/framework-conventions.md` — they're what diagnostics enforce.

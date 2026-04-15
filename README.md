# simple_module_python

A modular-monolith framework for Python. Each feature lives in its own self-contained module — its own SQLAlchemy models, schema, FastAPI endpoints, React pages — but everything ships as one FastAPI + Inertia.js + React app. No microservice tax, no API-client glue; just plugin modules that compose at boot.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy async, Alembic
- **Frontend:** Inertia.js + React + Tailwind CSS 4, Vite HMR
- **Auth:** Local user management (email+password, cookie-based sessions) via fastapi-users
- **Tooling:** uv workspaces, Ruff, ty, Biome, pytest

## Quickstart

```bash
# 1. Install Python and JS deps
make install

# 2. Copy env template (defaults work for local SQLite dev)
cp .env.example .env

# 3. Start Postgres (skip if using SQLite — the default .env uses SQLite)
make docker-up

# 4. Run migrations
make migrate

# 5. Start API + Vite dev server in parallel
make dev
```

Hit `http://localhost:8000` — you land on the public page. `/users/login` is the email+password login, `/dashboard` is the authenticated home, `/products` is a fully-working example module.

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
| `make docker-up` / `docker-down` | Manage the Postgres container (SQLite needs no Docker) |

## Configuration

All settings are `SM_`-prefixed env vars. Defaults in `.env.example` cover local dev. Key knobs:

| Variable | Default | Notes |
|---|---|---|
| `SM_DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | Async URL. Postgres: `postgresql+asyncpg://...` |
| `SM_ENVIRONMENT` | `development` | Anything else triggers strict module discovery |
| `SM_SECRET_KEY` | _(placeholder)_ | **Must** change in production — signs session cookies |
| `SM_USERS_ALLOW_SIGNUP` | `false` | Enable public signup (else admin-invite only) |
| `SM_USERS_MAILER` | `console` | `console` logs links; `smtp` uses SMTP config (see `.env.example`) |
| `SM_USERS_RESET_PASSWORD_TOKEN_SECRET` | _(dev placeholder)_ | **Must** change in production |
| `SM_USERS_VERIFICATION_TOKEN_SECRET` | _(dev placeholder)_ | **Must** change in production |
| `SM_USERS_BOOTSTRAP_EMAIL` | `` | First-admin email; combined with `SM_USERS_BOOTSTRAP_PASSWORD`, creates admin on first boot iff users table is empty |
| `SM_USERS_BOOTSTRAP_PASSWORD` | `` | Paired with above |
| `SM_MULTI_TENANT` | `false` | Set `true` to enable `TenantMiddleware` |
| `SM_TENANT_HEADER` | `` | Empty = token-only; set e.g. `X-Tenant-ID` to enable header fallback |

See `framework-conventions.md` for the settings-per-module convention.

## User management

### Creating the first admin

Either use the CLI:

```bash
uv run sm-users create-admin --email admin@example.com --password changeme
```

Or let the app bootstrap it automatically on first boot by setting env vars **before** running `make migrate && make dev`:

```
SM_USERS_BOOTSTRAP_EMAIL=admin@example.com
SM_USERS_BOOTSTRAP_PASSWORD=changeme
```

The auto-bootstrap is idempotent — it only creates the user if the `users_user` table is empty.

### Inviting users

1. Log in as admin and navigate to `/users/admin/invite`.
2. Fill in the invitee's email and optionally a full name and role(s). Click **Send invite**.
3. With the default `console` mailer, the invite link is logged to stdout (`tail -f` the server log). Copy the link and send it to the user. With `smtp`, the email is delivered automatically.
4. The invitee opens the link (`/users/invite/accept?token=…`), sets a password, and is immediately logged in.

### Enabling public signup

Set `SM_USERS_ALLOW_SIGNUP=true` and restart the server. The `/users/register` page becomes accessible.

### Switching to SMTP

```
SM_USERS_MAILER=smtp
SM_USERS_BASE_URL=https://your-domain.com
SM_USERS_SMTP_HOST=smtp.example.com
SM_USERS_SMTP_PORT=587
SM_USERS_SMTP_USERNAME=no-reply@example.com
SM_USERS_SMTP_PASSWORD=secret
SM_USERS_SMTP_FROM=no-reply@example.com
SM_USERS_SMTP_TLS=true
```

## Architecture

- **Modules**: discovered via Python entry points at boot. Each module subclasses `ModuleBase` and opts into the lifecycle hooks it needs (`register_routes`, `register_menu_items`, `register_permissions`, `register_middleware`, `on_startup`, ...).
- **Database isolation**: PostgreSQL → one schema per module. SQLite → single schema, `__tablename__` prefixed with the module name.
- **Middleware pipeline** (LIFO order of execution): CorrelationId → RequestLogging → SecurityHeaders → Session → `<module middleware>` → Tenant (opt-in) → InertiaLayoutData → app.
- **Diagnostics**: `make doctor` runs a static analyzer over installed modules looking for orphan pages, phantom renders, empty modules, framework/plugin coupling, and migration drift. Errors fail the boot in production.

Deeper dives in `docs/plans/`:

- [Module lifecycle hooks](docs/superpowers/specs/2026-04-13-module-lifecycle-hooks-design.md)
- [Alembic migrations design](docs/plans/2026-04-13-alembic-migrations-design.md)
- [DB state refactor](docs/plans/2026-04-13-eliminate-global-mutable-db-state-design.md)
- [DX hardening (latest)](docs/plans/2026-04-14-dx-hardening-design.md)

## Contributing

- Write tests with the fixtures in `conftest.py` (`db_session`, `authenticated_client`).
- Lint with `make lint` before pushing; CI runs all four checks in parallel.
- Stick to the conventions in `docs/framework-conventions.md` — they're what diagnostics enforce.

# simple_module_python

A modular-monolith framework for Python. Each feature lives in its own self-contained module — its own SQLModel tables, FastAPI endpoints, React pages — but everything ships as one FastAPI + Inertia.js + React app. No microservice tax, no API-client glue; just plugin modules that compose at boot.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLModel (SQLAlchemy async + Pydantic), Alembic
- **Frontend:** Inertia.js + React + Tailwind CSS 4, Vite HMR
- **UI:** shadcn/ui primitives + emerald/teal design tokens, Sora display font, DM Sans body, JetBrains Mono code
- **Auth:** Pluggable providers — local users (email+password + OAuth/OIDC: Google, GitHub, Microsoft/Entra) via fastapi-users, or Keycloak OIDC SSO; cookie sessions or bearer tokens resolved through a principal-resolver chain
- **Tooling:** uv workspaces, Ruff, ty, Biome, pytest

## Use in a new project

If you want to **build an app on simple_module**, not hack on the framework itself:

```bash
uvx --from simple_module_cli smpy new my-app
cd my-app
make dev
```

That scaffolds a working FastAPI + Inertia + React app with `users`, `dashboard`, and `permissions` pre-wired. You land on `/users/login`, sign in with the admin account you bootstrap, and go from there.

See [CHANGELOG.md](CHANGELOG.md) for the list of published PyPI / npm packages at each release.

---

## Quickstart

```bash
# 1. Install Python and JS deps
make install

# 2. Copy env template (defaults work for local SQLite dev)
cp .env.example .env

# 3. Start the shared dev-services stack — Postgres/Redis/MinIO (skip if using the default SQLite)
make docker-up

# 4. Run migrations
make migrate

# 5. Start API + Vite dev server in parallel
make dev
```

Hit `http://localhost:8000` — you land on the public page. `/users/login` is the email+password login, `/dashboard/` is the authenticated home, and `/admin/doctor/` is the admin-only "smpy doctor" panel (static checks, migrations, dev server, modules).

## Run it in Docker

The repo ships a default image (`./Dockerfile`) that builds the host plus every
bundled module — Python workspace, `gen-pages`, and the production Vite bundle —
and serves it with uvicorn. It is standalone: SQLite lives inside the container
under `/app/data`, so no Postgres and no Redis are needed to boot.

```bash
make docker-app        # build ./Dockerfile, then run it on http://localhost:8000
```

Both run targets take `SM_APP_PORT=8010` when a `make dev` already holds
8000.

or without make:

```bash
docker build -t simple-module-python .
docker run --rm -p 8000:8000 -v simple-module-python-data:/app/data simple-module-python
```

**Logging in.** With no `SM_USERS_BOOTSTRAP_*` set, the container seeds
**`admin@example.com` / `changeme`** — the same pair `.env.example` uses for
local dev — and says so on every boot that uses it:

```
entrypoint: WARNING - no SM_USERS_BOOTSTRAP_PASSWORD set, so the
entrypoint: first-boot admin is the public default:
entrypoint:     admin@example.com / changeme
```

Pass `-e SM_USERS_BOOTSTRAP_EMAIL=… -e SM_USERS_BOOTSTRAP_PASSWORD=…` to seed
your own instead, and change it before the container is reachable by anyone but
you. The seed only applies while the users table is empty, so on a reused volume
the existing password still stands — reset it with
`smpy users create-admin --email … --password … --force`.

`make docker-compose-app` (or `docker compose up --build app`) runs the same
image through compose with a named volume — independent of the shared
dev-services stack that `worker`/`beat` use.

What the entrypoint does before uvicorn binds: applies `alembic upgrade heads`
(a fresh volume has no tables, and production fails boot on `SM010` when the DB
is behind head), and generates an ephemeral `SM_SECRET_KEY` when none is set —
enough to boot and log in, but sessions die on restart, so set one for anything
real.

The image runs with `SM_ENVIRONMENT=production` because it serves the built
bundle rather than a Vite dev server. Useful overrides:

| Variable | Image default | Why you'd change it |
|---|---|---|
| `SM_SECRET_KEY` | generated per start | Persist sessions across restarts |
| `SM_DATABASE_URL` | `sqlite+aiosqlite:////app/data/app.db` | Point at Postgres |
| `SM_USERS_BOOTSTRAP_EMAIL` / `_PASSWORD` | `admin@example.com` / `changeme` | Seed a first admin nobody else can guess |
| `SM_TRUSTED_PROXY` | unset | Set to `*` behind a TLS-terminating reverse proxy |

**No background tasks.** The image skips installing the Celery module
(`uv sync … --no-install-package simple-module-background-tasks`), so nothing in
it wants a broker — a queue means a second process and a Redis, which is the
opposite of a standalone image. `docker-compose.yml`'s `worker` / `beat`
services cover that path: they build `docker/worker.Dockerfile` against the
shared `../dev-services` Postgres + Redis on the external `devnet` network. To
run tasks from the web process instead, drop the `--no-install-package` flag
from the Dockerfile and set `SM_BG_TASKS_BROKER_URL` / `_RESULT_BACKEND`.

## Create a new module

```bash
make new-module name=orders
```

That scaffolds `modules/orders/` with a working CRUD module end-to-end — `ModuleMeta`, SQLModel table with `AuditMixin`, SQLModel contracts, service layer, REST + Inertia view endpoints, `Browse/Create/Edit.tsx` pages, and tests. Next:

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
  cli/         # smpy CLI — scaffolding, skills, package updates
  core/        # module system, discovery, events, diagnostics
  db/          # per-module Base, session, mixins, listeners
  hosting/     # app_builder, middleware, settings, Inertia glue
  testing/     # shared pytest fixtures + helpers
modules/       # plugin modules (auth, dashboard, users, settings, ...)
host/
  main.py      # FastAPI entry point
  routes.py    # host-level routes (landing page)
  client_app/  # Vite + React client app
  migrations/  # Alembic migrations
packages/
  ui/          # shared shadcn/ui components, layouts, and design-system primitives
  i18n/        # generated i18n keys + translation runtime
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
| `make kill` | Stop any running dev servers (ports 8000, 5050, 5173) |
| `make docker-build` / `docker-app` | Build the default app image / run it standalone on port 8000 |
| `make docker-up` / `docker-down` | `docker-up` brings up the shared dev-services stack (Postgres/Redis/MinIO); `docker-down` stops only this repo's worker/beat (SQLite needs no Docker) |

## Configuration

Local deployments only need one env var — everything else has sensible defaults and is managed in the admin UI at `/admin/settings/`.

| Variable | Default | Required |
|---|---|---|
| `SM_DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | Yes — async URL. Postgres: `postgresql+asyncpg://...` |
| `SM_ENVIRONMENT` | `development` | No — any value other than `development`, `test`, `testing` triggers strict discovery and placeholder-secret checks |
| `SM_SECRET_KEY` | `change-me-in-production` | No in dev; **must** be overridden in production |
| `SM_VITE_DEV_URL` | `http://localhost:5050` | Dev only — Vite HMR origin |
| `SM_AUTH_PROVIDER` | `users` | No — `users` or `keycloak`. Only read when both are installed; see [Auth providers](#auth-providers-users-or-keycloak) |

Power users can still override the following bootstrap knobs via env if needed: `SM_DB_POOL_SIZE`, `SM_DB_MAX_OVERFLOW`, `SM_DB_POOL_PRE_PING`, `SM_DB_POOL_RECYCLE`, `SM_DEBUG`, `SM_LOG_LEVEL`, `SM_LOG_FORMAT`, `SM_MODULES_ENABLED`. These are needed before the DB connection is open.

All module-level settings — users, SMTP, Celery broker, file storage backend, etc. — live in the admin UI. After upgrading an existing deployment, run once:

```bash
uv run smpy settings import-from-env
```

to seed DB overrides from the current `SM_*` environment.

> **docker-compose note:** `docker-compose.yml` sets a few `SM_BG_TASKS_*` vars so Celery can reach the `redis` service by container hostname before the DB-backed settings are loaded. That's deployment plumbing — not a module config knob.

See `framework-conventions.md` for the settings-per-module convention.

## UI & design system

The frontend uses an emerald + teal design system mirrored as Tailwind 4 tokens. Module pages should compose from a small set of shared primitives so they stay visually consistent without duplication.

**Shared primitives** (in `packages/ui/src/`):

| Component | When to use |
|---|---|
| `PageShell` | Every authenticated page. Wraps title + description + actions header and a max-width content area. |
| `StatCard` | Top-of-page KPI tiles — icon, value, label, optional delta badge. Used on Dashboard, Users, Doctor. |
| `SectionTitle` | Card section headings with the gradient accent bar. |
| `FilterPills` | Segmented filter chips for status/tab-style toggles. |
| `AuthCardShell` | Login / register / forgot / accept-invite / verify — light glass card on emerald mesh blobs. |
| `ErrorScreen` | 403 / 404 / 500 — gradient HTTP numerals + accent badge per status. |

**Design tokens** live in `packages/ui/src/styles/globals.css` under the `@theme` block — primary emerald scale (`--color-primary-50…900`), display/sans/mono families, semantic shadcn tokens. Override the CSS variables to rebrand without touching component code.

**Module pages** should:

- Wrap in `PageShell` with `title`, optional `description`, and `actions`.
- Use `Card` + `CardContent` from `@simple-module-py/ui/components/ui/card` for content blocks.
- Reach for `StatCard` / `SectionTitle` / `FilterPills` before rolling new layouts.
- Use lucide-react icons (already a dependency) and the existing `Badge` / `Button` variants — emerald primary for the main CTA, outline / ghost for secondary actions.

The 300-line file cap (enforced by CI) usually pushes you to factor row-level components into `pages/components/` — see `modules/users/users/components/UserRow.tsx` and `modules/dashboard/dashboard/pages/components/doctor-data.ts` for the pattern.

## User management

### Auth providers: users **or** keycloak, never both

This repo ships two authentication providers, and **exactly one can be active at a time**:

| Module | What it does |
|---|---|
| `users` (default) | Local accounts — password login, invites, signup, roles, an admin UI |
| `keycloak` | Delegates authentication to a Keycloak realm over OIDC |

Both claim the same slot (`app.state.auth.auth_provider`), so running them together
is a misconfiguration, not a supported combination. Installing both and activating
neither is reported as `SM020` (error — fails boot); installing neither is `SM021`.

`uv sync --all-packages` installs *every* workspace member, so a dev clone has both
packages on disk. The host therefore activates one and skips the other rather than
failing on `SM020`, and **`users` is the default** — `keycloak` is installed but inert
until you ask for it. To switch:

```bash
# .env
SM_AUTH_PROVIDER=keycloak
```

Then re-run `make gen-pages` so the frontend manifest picks up the active provider's
pages (`make dev` does this for you), and configure the realm under
`/admin/settings/`. Switching back is the same knob set to `users`.

Two caveats when running Keycloak:

- `dashboard`, `permissions`, `audit_log`, and `background_tasks` declare a
  dependency on the `Users` **module** and import from the `users` package, so
  `simple_module_users` still has to be installed even though it is inactive. A
  host that wants Keycloak *and* none of the local-account machinery should leave
  those modules out of its own dependency list.
- The local-account flows (`/users/login`, invites, signup, the sections below)
  belong to the `users` module and are gone while Keycloak is active — Keycloak's
  realm owns login, logout, and user administration instead.

Only one provider is ever discovered, so nothing here changes if you install just one
of the two: a host that ships only `keycloak` keeps it regardless of `SM_AUTH_PROVIDER`.

### Creating the first admin

Either use the CLI:

```bash
uv run smpy users create-admin --email admin@example.com --password changeme
```

Or let the app bootstrap it automatically on first boot by setting env vars **before** running `make migrate && make dev`:

```
SM_USERS_BOOTSTRAP_EMAIL=admin@example.com
SM_USERS_BOOTSTRAP_PASSWORD=changeme
```

The auto-bootstrap is idempotent — it only creates the user if the `users_user` table is empty.

### Inviting users

1. Log in as admin and navigate to `/admin/users/add`.
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
- **Database**: a single shared schema on both Postgres and SQLite. Each module owns its own `MetaData` (so Alembic can attribute tables to it), and `__tablename__` is prefixed with the module name (`orders_order`) to avoid collisions.
- **Middleware pipeline** (LIFO order of execution): CorrelationId → RequestLogging → SecurityHeaders → Session → `<module middleware>` → Tenant (opt-in) → Locale → InertiaLayoutData → app.
- **Diagnostics**: `make doctor` runs a static analyzer over installed modules looking for orphan pages, phantom renders, empty modules, framework/plugin coupling, migration drift, and locale-file consistency. Errors fail the boot in production.
- **Internationalization**: per-module `locales/<lang>.json` files merged at boot into `I18nRegistry`. Frontend uses `i18next` with type-safe keys; backend uses `Babel` for CLDR plurals. Locale resolved per request via cookie → `Accept-Language` → `SM_I18N_DEFAULT_LOCALE`. See `docs/framework-conventions.md` → Internationalization.

Full documentation lives in [`docs/`](docs/index.md) — a VitePress site covering the guide, framework internals, database, frontend, testing, every bundled module, and reference. When conventions are ambiguous, the authoritative single-pagers are the source of truth:

- [Framework conventions](docs/framework-conventions.md)
- [Module authoring](docs/module-authoring.md)
- [E2E testing](docs/e2e-testing.md)
- [Release playbook](docs/release.md)

Historical, point-in-time design docs live under [`docs/plans/`](docs/plans/) and [`docs/superpowers/`](docs/superpowers/).

## Contributing

- Write tests with the fixtures from the `simple_module_test` plugin (`db_session`, `authenticated_client`).
- Lint with `make lint` before pushing; CI runs all four checks in parallel.
- Stick to the conventions in `docs/framework-conventions.md` — they're what diagnostics enforce.

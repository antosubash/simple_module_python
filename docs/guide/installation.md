# Installation

## Prerequisites

| Tool | Why | How to check |
|---|---|---|
| **Python 3.12** | Runtime | `python --version` |
| **[uv](https://docs.astral.sh/uv/)** | Python package manager + venv | `uv --version` |
| **Node.js 20+** | Vite dev server, React build | `node --version` |
| **npm 10+** | JS workspace manager | `npm --version` |
| **Docker** (optional) | Postgres in a container (SQLite works without) | `docker --version` |
| **Make** | Task runner — all day-to-day commands flow through this | `make --version` |

On macOS, `brew install uv node make` and Docker Desktop will cover it. On Linux, install uv with the install script and Node via `nvm` or your package manager.

## Clone and install

```bash
git clone https://github.com/antosubash/simple_module_python.git
cd simple_module_python
make install
```

`make install` runs:

- `uv sync --all-packages` — installs every Python package in the workspace (framework, modules, host) into a single `.venv`.
- `npm install` — installs JS deps for `host/client_app`, `packages/*`, and every module that ships a `package.json`.

Installation takes 1–2 minutes on a warm cache.

## Env configuration

```bash
cp .env.example .env
```

The defaults in `.env.example` work for local SQLite dev. The only variable you'll likely change is `SM_DATABASE_URL` if you're using Postgres:

```bash
# SQLite (default) — zero setup
SM_DATABASE_URL=sqlite+aiosqlite:///./app.db

# Postgres (requires make docker-up)
SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/simple_module
```

See [Configuration](/guide/configuration) for the full list of env vars.

## Database setup

### SQLite (no Docker)

```bash
make migrate
```

Creates `app.db` in the repo root and stamps it at the Alembic head.

### Postgres (via Docker)

```bash
make docker-up     # starts Postgres + Redis
make migrate
```

The compose file sets up a `postgres` service on port 5432 and a `redis` service on 6379 (used by the `background_tasks` module's Celery broker).

## Sanity check

```bash
make dev
```

In parallel, this starts:

- `uvicorn host.main:app` on `:8000` (the FastAPI + Inertia app)
- `vite` on `:5050` (the frontend dev server with HMR)

Hit `http://localhost:8000`. You should see the landing page. Stop both servers with `make kill`.

## Create the first admin

```bash
uv run sm-users create-admin --email admin@example.com --password changeme
```

Or set bootstrap env vars so the admin is auto-created on first boot:

```bash
# in .env
SM_USERS_BOOTSTRAP_EMAIL=admin@example.com
SM_USERS_BOOTSTRAP_PASSWORD=changeme
```

Then `make migrate && make dev`.

## Install Playwright (optional — for E2E)

```bash
uv run playwright install chromium
```

E2E tests are off by default (the root `pyproject.toml` pins `-m 'not e2e'`). Run them explicitly with `make test-e2e` while a dev server is running. See [E2E testing](/e2e-testing).

## Troubleshooting

**`make dev` says a port is in use.**
Run `make kill` to free ports 8000 and 5050.

**Alembic complains about revision mismatch.**
Your local DB is ahead of or behind the migration files. For a dev DB, `rm app.db && make migrate`. For Postgres, `make docker-down && make docker-up && make migrate`.

**Entry points aren't discovered after editing a module's `pyproject.toml`.**
Re-run `uv sync --all-packages` (or just `make install`) — entry points are registered at install time, not at import time.

**Diagnostics fail with `SM009`.**
You wrote `from <module_name> import …` inside `framework/*`. Framework code must not reach into plugin modules — invert the dependency (register a callback from the module) or promote the shared concept into `framework/`.

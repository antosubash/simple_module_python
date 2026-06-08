# Installation

You install simple_module_python by installing its **CLI** — `smpy` — and using it to scaffold a new app. There's no repo to clone; the framework ships as a set of Python packages on PyPI and the CLI assembles them into a working project for you.

## Prerequisites

| Tool | Why | How to check |
|---|---|---|
| **Python 3.12** | Runtime | `python --version` |
| **[uv](https://docs.astral.sh/uv/)** | Python package manager + tool installer | `uv --version` |
| **Node.js 20+** | Vite dev server, React build | `node --version` |
| **npm 10+** | JS workspace manager | `npm --version` |
| **Docker** (optional) | Postgres + Redis when you don't want SQLite | `docker --version` |

On macOS, `brew install uv node` plus Docker Desktop covers it. On Linux, install uv via the install script and Node via `nvm` or your package manager.

## Install the CLI

```bash
uv tool install simple_module_cli
```

If you prefer pipx:

```bash
pipx install simple_module_cli
```

That puts `smpy` on your PATH globally. Confirm with:

```bash
smpy --help
```

## Scaffold a new app

```bash
smpy new myapp
```

Interactive — you pick the database (SQLite / Postgres), whether to enable multi-tenancy, and which bundled modules to include. Skip the prompts and accept the defaults with:

```bash
smpy new myapp --yes
```

Or pick a preset and add modules non-interactively:

```bash
smpy new myapp --preset standard --with background_tasks,file_storage
```

| Preset | Modules |
|---|---|
| `minimal` | `auth`, `users` |
| `standard` (default) | `minimal` + `dashboard`, `permissions` |
| `full` | `standard` + `settings`, `feature_flags`, `file_storage`, `background_tasks` |

Dependencies between modules are resolved automatically — e.g. `users` always pulls in `auth`, and `file_storage` pulls in `settings`. The `settings` module ships only in the `full` preset (or when added explicitly with `--with settings`).

After scaffolding, `smpy new` runs `uv sync`, `npm install`, and `alembic upgrade head` for you (skip with `--no-install` if you'd rather drive that yourself).

## Boot it

```bash
cd myapp
make dev
```

The scaffolded app ships with a small Makefile that runs the API + Vite dev server in parallel:

- `uvicorn main:app` on `:8000` (the FastAPI + Inertia app)
- `vite` on `:5050` (the frontend dev server with HMR)

Hit `http://localhost:8000`. You should see the landing page.

## Database choice

`smpy new` writes a `.env.example`. The default is SQLite (zero setup):

```bash
SM_DATABASE_URL=sqlite+aiosqlite:///./app.db
```

For Postgres, scaffold with `--db postgres` (or pick Postgres in the wizard) and `smpy new` writes a matching `SM_DATABASE_URL`:

```bash
SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/myapp
```

A `docker-compose.yml` is only generated when you include the `background_tasks` module; it brings up `postgres` (db `simple_module`, user `sm`/`sm`) on `:5432`, `redis` on `:6379`, and the `host`/`worker`/`beat` services:

```bash
docker compose up -d postgres
make migrate
```

Without `background_tasks`, bring your own Postgres (or stay on the default SQLite). See [Configuration](/guide/configuration) for the full list of env vars.

## Create the first admin

If you included the `users` module:

```bash
uv run smpy users create-admin --email admin@example.com --password changeme
```

Or set bootstrap env vars so the admin is auto-created on first boot:

```bash
# in .env
SM_USERS_BOOTSTRAP_EMAIL=admin@example.com
SM_USERS_BOOTSTRAP_PASSWORD=changeme
```

Then `make migrate && make dev`.

## Add a module to your app

```bash
smpy create-module orders --dest modules/orders
```

That generates a publishable module package at `modules/orders/` with the starter layout — `module.py` (its `ModuleBase` subclass + entry point), `services.py`, `settings.py`, a REST `endpoints/api.py`, an empty `pages/` dir, tests, and `pyproject.toml`/`package.json`/`tsconfig.json`. Flesh out models, contracts, views, and pages as your domain needs them. Add the package to your app's dependencies and re-sync:

```bash
uv add ./modules/orders
make dev
```

The full walkthrough is in [Your first module](/guide/first-module).

## Update framework versions

When new releases of `simple_module_*` ship to PyPI, bump every dep in lockstep:

```bash
smpy package-update
```

Pass `--dry-run` first to preview the diff.

## Troubleshooting

**`smpy: command not found`** after `uv tool install`.
Run `uv tool update-shell` (or restart your shell) so the tool's bin dir is on PATH.

**Port already in use.**
Free `:8000` and `:5050` before the next `make dev`. On Linux/macOS: `lsof -ti:8000,5050 | xargs kill -9`.

**Alembic complains about a revision mismatch.**
The DB is ahead of or behind the migration files. For a dev DB: `rm app.db && make migrate`. For Postgres: `docker compose down -v && docker compose up -d postgres && make migrate`.

**Entry points aren't discovered after editing a module's `pyproject.toml`.**
Re-run `uv sync` — entry points are registered at install time, not at import time.

## Next steps

- [Quickstart](/guide/quickstart) — bootstrap and tour the running app in five minutes.
- [Project structure](/guide/project-structure) — what `smpy new` lays down.
- [Your first module](/guide/first-module) — extend the app with your own domain logic.
- [Bundled modules](/modules/) — what each pre-installed module ships.

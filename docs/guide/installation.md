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

`simple_module_settings` is also installed as a baseline dependency of every scaffolded host (regardless of preset), so the Settings admin UI is available even in `minimal`. Dependencies between modules are resolved automatically — e.g. `users` always pulls in `auth`.

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

For Postgres:

```bash
SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/myapp
```

The scaffolded `docker-compose.yml` brings up a `postgres` container on `:5432` (and a `redis` container on `:6379` when you include `background_tasks`):

```bash
docker compose up -d postgres
make migrate
```

See [Configuration](/guide/configuration) for the full list of env vars.

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

That generates `modules/orders/` with the full layout (model, contracts, service, endpoints, pages, tests, locales, `pyproject.toml` entry point). Add the package to your app's dependencies and re-sync:

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

**`sm: command not found`** after `uv tool install`.
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

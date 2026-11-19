# Installation

You install simple_module_python by installing its **CLI** — `uv run smpy` — and using it to scaffold a new app. There's no repo to clone; the framework ships as a set of Python packages on PyPI and the CLI assembles them into a working project for you.

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

That installs the `smpy` executable. Run it through `uv run` to use the app environment. Confirm with:

```bash
uv run smpy --help
```

Already installed? `uv tool upgrade simple_module_cli` (or `pipx upgrade simple_module_cli`). A new app pins the framework to the CLI's own version, so an old CLI scaffolds an old app; `uv run smpy new` warns when PyPI has a newer one.

## Scaffold a new app

```bash
uv run smpy new myapp
```

Interactive — you pick the database (SQLite / Postgres), whether to enable multi-tenancy, and which bundled modules to include. Skip the prompts and accept the defaults with:

```bash
uv run smpy new myapp --yes
```

Or pick a preset and add modules non-interactively:

```bash
uv run smpy new myapp --preset standard --with background_tasks,file_storage
```

| Preset | Modules |
|---|---|
| `minimal` | `auth`, `users` |
| `standard` (default) | `minimal` + `dashboard`, `permissions` |
| `full` | `standard` + `settings`, `feature_flags`, `file_storage`, `background_tasks` |

Dependencies between modules are resolved automatically — e.g. `users` always pulls in `auth`, and `file_storage` pulls in `settings`. The `settings` module ships only in the `full` preset (or when added explicitly with `--with settings`).

After scaffolding, `uv run smpy new` runs `uv sync --all-packages` (`uv sync` for `--flat`), `npm install`, and `alembic upgrade heads` for you. With `--no-install` it prints those steps instead, starting with `make install`.

## Boot it

```bash
cd myapp
make dev
```

The scaffolded Makefile delegates to `uv run smpy dev`, which generates frontend artifacts before starting both servers:

- `uvicorn main:app` on `:8000` (the FastAPI + Inertia app)
- `vite` on the first free port starting at `:5050` (the frontend dev server with HMR)

Hit `http://localhost:8000`. You should see the landing page. Use `uv run smpy dev --port 8010` for a second app; add `--vite-port 5201` only when you need a fixed Vite port. Ctrl-C or SIGTERM cleans up both owned process groups, including reload workers. A child exiting also stops its sibling. Python is the dotenv reader; exported variables win over file values, and the selected Vite URL is passed to both children.

## Database choice

`uv run smpy new` writes a committed `.env.example` (placeholders only) and a gitignored `.env` holding the generated secrets. The default is SQLite (zero setup):

```bash
SM_DATABASE_URL=sqlite+aiosqlite:///./app.db
```

For Postgres, scaffold with `--db postgres` (or pick Postgres in the wizard) and `uv run smpy new` writes a matching `SM_DATABASE_URL`:

```bash
POSTGRES_PASSWORD=<generated>
SM_DATABASE_URL=postgresql+asyncpg://postgres:<generated>@localhost:5432/my_app
```

The database name is the snake_case app name. `POSTGRES_PASSWORD` is shared with the compose `postgres` service below. Compose interpolates it unencoded into the container's `SM_DATABASE_URL`, so it must be URL-safe (letters, digits, `-`, `_`, `.`, `~`); `make docker-up` refuses to start otherwise. The generated value always is.

Every scaffold ships a `docker-compose.yml` that matches your `--db` choice (a migration history is dialect-frozen at autogenerate time, so containers must run the same database the migrations were generated against). With `--db postgres` it brings up `postgres` (db named after your app, user `postgres`, password from `POSTGRES_PASSWORD` in `.env`) on `127.0.0.1:5432` and the `app` service; the default SQLite scaffold runs the `app` container alone with the database on a named volume. Including the `background_tasks` module adds `redis` on `127.0.0.1:6379` plus `worker`/`beat` services that reuse the app image. With `--db postgres`, the container also doubles as a local dev database:

```bash
docker compose up -d postgres
make migrate
```

Or run the whole stack in containers — `make docker-up` builds the image (`docker/host.Dockerfile`), applies migrations on start, and serves on `:8000` with `SM_ENVIRONMENT=production`. See [Configuration](/guide/configuration) for the full list of env vars.

## Create the first admin

If you included the `users` module:

```bash
uv run smpy users create-admin --email admin@example.com
```

It prompts for the password; `--password` is for scripts and ends up in your shell history.

Or set bootstrap env vars so the admin is auto-created on first boot:

```bash
# in .env
SM_USERS_BOOTSTRAP_EMAIL=admin@example.com
SM_USERS_BOOTSTRAP_PASSWORD=changeme
```

Then `make migrate && make dev`.

## Add a module to your app

```bash
uv run smpy create-module orders --dest modules/orders
```

That generates a publishable module package at `modules/orders/` with the starter layout — `module.py` (its `ModuleBase` subclass + entry point), `core/constants.py` (add `--with-settings` for `core/settings.py` and `core/services.py`), a REST `web/endpoints/api.py`, CRUD pages, locales, tests, and `pyproject.toml`. The host generates TypeScript configs; an authored `tsconfig.json` is an optional override. Add a dependency-only `package.json` inside the Python package only for extra JS dependencies, then run `uv run smpy host sync-js-deps` (also needed for editable installs). Flesh out models, contracts, views, and pages as your domain needs them. Inside an app workspace it is wired and installed automatically. Generate and review its migration, apply it and restart:

```bash
uv run smpy migrations new orders -m "add orders tables"
make migrate
make dev
```

`create-module` syncs Python and npm dependencies from the app root and runs
`uv run smpy gen`. In a flat app, wire the standalone module with
`uv run smpy add ./modules/orders`, then `make install`. The migration command
uses the module's branch head, or creates its first labelled root. Review the
revision before applying it; autogenerate sees all installed module metadata.

The full walkthrough is in [Your first module](/guide/first-module).

## Update framework versions

Update framework/module pins from PyPI and git with one command:

```bash
uv run smpy update
```

Pass `--dry-run` first to preview the diff. The command scans the root and uv
workspace members: project dependencies, every optional-dependency extra and
every dependency group, including workspace roots with only dev groups.
Projects matching `[tool.uv.workspace].exclude` (exact paths or globs) are skipped.
Include-group objects and workspace/local uv sources are left alone; source
names are normalized and member sources override root sources.
Naming one PyPI distribution published with this framework updates its framework
and bundled-module PyPI siblings together to keep their pins aligned; a skipped
PyPI sibling refuses the update before writes. Independently released packages
such as `simple_module_images` are selected individually and do not join this cohort.

It also scans each root/member `package.json` and `client_app/package.json`, in
`dependencies`, `devDependencies`, `optionalDependencies` and `peerDependencies`.
`@simple-module-py/*` pins follow the selected `simple_module_core` release
in lockstep, preserving exact, `^` or `~` style and never downgrading. The npm
registry must contain that exact version; unavailable releases, incompatible
version spellings, unsupported ranges and workspace/file/git/alias references
are reported as skips, and so is every npm pin when the run leaves the Python
`simple_module_core` pin alone (an upper bound or a local source), so npm never
runs ahead of Python. `--include-pre` also applies to core target selection.
Python releases use PEP 440 ordering: RC numbers advance numerically, and a final
release outranks its RCs, so stable-only updates can promote an RC pin to final.
Existing pins never move backwards.

All manifests are parsed and changes planned before any writes. Dry runs write
nothing; JSON indentation and trailing-newline style are preserved. Writes to
multiple files are not atomic against filesystem errors. The command then syncs lockfiles with `uv sync` (workspace apps:
`uv sync --all-packages` from the app root), `npm install` where the frontend
lives, then `uv run smpy gen`. Python-only hosts skip the frontend steps.
Failures stop the command; fix the error and rerun. Git tag sources update
in groups per repository, branch sources refresh their SHA, and immutable revs
stay pinned. The deprecated `package-update` alias is removed in 0.0.50.

Each constraint keeps the operator you wrote — `==0.0.32` becomes `==0.0.33`,
`>=0.0.32` becomes `>=0.0.33` — so bumping versions never changes your pinning
policy. That matters because the published module wheels pin their framework
deps exactly: a host loosened to `>=` hands the effective version to whichever
wheel pins hardest, rather than deciding it itself.

Two consequences worth knowing:

- A dependency whose upper bound excludes the latest release (`>=0.1,<1.0`
  when 2.0.0 is out) is reported and left alone, rather than having its ceiling
  silently dropped.
- A dependency with no constraint at all has no pin style to preserve, so it
  gets `>=<latest>`.

Pass `--loosen` to rewrite every Python constraint to `>=<latest>` instead.

## Troubleshooting

**`uv run smpy: command not found`** after `uv tool install`.
Run `uv tool update-shell` (or restart your shell) so the tool's bin dir is on PATH.

**Port already in use.**
Vite automatically skips occupied ports. For an occupied API port, use `make dev ARGS="--port 8010"`. An explicit `--vite-port` fails when occupied rather than silently moving. Stop a previous `uv run smpy dev` with Ctrl-C or SIGTERM to its supervisor PID; `make kill` only prints this guidance and never kills other projects by port or process name.

**Alembic complains about a revision mismatch.**
The DB is ahead of or behind the migration files. For a dev DB: `rm app.db && make migrate`. For Postgres: `docker compose down -v && docker compose up -d postgres && make migrate`.

**Entry points aren't discovered after editing a module's `pyproject.toml`.**
Re-run `make install` (`uv sync --all-packages`) — entry points are registered at install time, not at import time. Then restart `make dev`: a reload keeps the import path the server started with.

## Next steps

- [Quickstart](/guide/quickstart) — bootstrap and tour the running app in five minutes.
- [Project structure](/guide/project-structure) — what `uv run smpy new` lays down.
- [Your first module](/guide/first-module) — extend the app with your own domain logic.
- [Bundled modules](/modules/) — what each pre-installed module ships.

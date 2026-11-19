# Project structure

`uv run smpy new myapp` lays down a uv + npm **workspace** by default. The workspace root holds shared config; the runnable app lives under `host/`; your own modules live as workspace members under `modules/` (seeded with a sample `hello` module).

```text
myapp/
├── pyproject.toml             # uv workspace root (members: host, modules/*) — not itself installed
├── package.json               # npm workspace root (host/client_app, modules/*)
├── .env.example               # committed template, no secrets
├── .env                       # generated secrets (gitignored)
├── Makefile                   # thin wrapper: install / dev / migrate / build / gen
├── README.md
│
├── host/                      # the runnable application
│   ├── main.py                # FastAPI entry point — build_host_app
│   ├── routes.py
│   ├── pyproject.toml          # host deps (uv-managed): hosting + selected modules
│   ├── alembic.ini             # Alembic config — points at migrations/
│   ├── Makefile
│   ├── client_app/             # Vite + React root
│   │   ├── main.tsx            # bootstrap
│   │   ├── app.tsx, pages.ts
│   │   ├── pages/              # host-level Inertia pages (Landing, Error)
│   │   ├── modules.generated.ts   # auto-generated page map — DO NOT EDIT
│   │   ├── modules.manifest.json  # auto-generated manifest — DO NOT EDIT
│   │   ├── modules.generated.css  # auto-generated module CSS — DO NOT EDIT
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── vite.config.ts
│   └── migrations/             # Alembic migrations for ALL modules
│       ├── env.py              # calls the framework run_migrations(context) runner
│       └── versions/
│
└── modules/                    # your workspace modules (uv run smpy create-module --dest modules/<name>)
    └── hello/                  # sample module scaffolded by uv run smpy new
        └── … (see "Anatomy of a module" below)
```

`uv run smpy new --flat` skips the workspace wrapper and the sample `hello` module, emitting a single-host layout (`main.py`, `client_app/`, `migrations/` at the top level) — use it when the app only consumes published modules and never authors its own. `uv run smpy new --preset minimal` ships fewer pre-installed modules. Every scaffold also ships Docker assets by default: a `docker/host.Dockerfile`, a `docker-compose.yml` matched to your `--db` choice (`app` on a SQLite volume, or `postgres` + `app`; plus `redis`/`worker`/`beat` when `background_tasks` is included), a `.dockerignore`, and `make docker-up` / `docker-build` / `docker-down` targets.

## Bundled modules

The framework's first-party modules live on PyPI as `simple_module_<name>` and are added to `pyproject.toml` by `uv run smpy new` based on the preset / `--with` you pick:

| Module | What it provides |
|---|---|
| `auth` | Tiny public API (`UserContext`, `get_current_user`) |
| `users` | Email + password login, sessions, roles, invites, admin UI |
| `permissions` | Role + direct-grant assignment store + `RequiresPermission` |
| `settings` | DB-backed key/value store + per-module pydantic settings + admin UI |
| `feature_flags` | Runtime feature toggles with system + tenant overrides |
| `file_storage` | Pluggable file storage (filesystem, S3) + browse/download UI |
| `background_tasks` | Celery + Redis workers, persistent task history, retry, worker dashboard |
| `dashboard` | Authenticated landing page |

See [Bundled modules](/modules/) for details on each.

## Anatomy of a module

Every bundled module and every scaffolded module uses the area layout;
[Module layout](/module-layout) has the full contract.

```text
modules/orders/
├── pyproject.toml
├── orders/
│   ├── __init__.py, py.typed, module.py
│   ├── models.py                 # or models/; discovered by name
│   ├── contracts/                # public SQLModel DTOs and extension contracts
│   ├── core/                     # constants.py, settings.py, services.py, errors.py
│   ├── web/                      # deps.py, service.py (or services/), private schemas
│   │   └── endpoints/            # api.py, views.py
│   ├── pages/                    # Inertia pages, generated API client + types
│   ├── locales/                  # <lang>.json
│   ├── ui/                       # components/, hooks/, utils/ (when needed)
│   └── tasks.py, theme.css, styles.css  # optional root lookup files
└── tests/
    ├── conftest.py                # module-wide fixtures
    ├── core/module/test_orders_module.py
    ├── core/contracts/test_orders_schemas.py
    └── web/crud/test_orders_crud.py
```

The host generates module TypeScript projects; authored `tsconfig.json` files are
optional overrides. Declare extra JS dependencies in a dependency-only
`package.json` inside the Python package so it ships in wheels. Run
`uv run smpy host sync-js-deps` to install those extras, including for editable installs.
Existing module-root npm workspace manifests remain supported.

Tests have no `__init__.py`; importlib mode allows repeated basenames.
The scaffold uses the `test_orders_` prefix. JS tests stay in `modules/orders/tests-js/`.

See the [module authoring guide](/module-authoring) for the full contract.

## Where things get generated

| File | Generated by | When |
|---|---|---|
| `host/client_app/modules.generated.ts` | `uv run smpy gen` (auto via install/dev/build) | Every time you add/remove a module page |
| `host/client_app/modules.manifest.json` | `uv run smpy gen` | Same |
| `host/client_app/modules.generated.css` | `uv run smpy gen` | Same |
| Host-owned module TypeScript projects | `uv run smpy gen` / `uv run smpy host typecheck` | For installed modules without authored overrides |
| `host/migrations/versions/XXXX_*.py` | `uv run smpy migrations new <module> -m "…"` | When you add/change SQLModel tables |
| `modules/<name>/**` | `uv run smpy create-module <name> --dest modules/<name>` | Scaffolding a new module |

`uv run smpy gen` also syncs module npm dependencies, regenerates i18n keys in the existing i18n package, and updates API types for local modules that already have a generated API file. Its local `.smpy/gen.json` cache checks input and output contents; an unchanged run touches no files.

Never hand-edit the `.generated.*` files — they are overwritten on the next `uv run smpy gen` run.

## Where things intentionally *don't* live

- **No per-module `migrations/` folder.** All migrations live in `host/migrations/versions/`. Autogenerate discovers every installed module's metadata through the framework runner in `host/migrations/env.py`. Each module's first migration sets a `branch_labels` marker, a named target for that revision (it does not make `alembic downgrade <module>@base` a per-module rollback; see [Migrations](/database/migrations)).
- **No host-level `api/` folder.** REST endpoints are attached by each module via `register_routes(api_router, view_router)`. `/api/*` is the union of every module's API router.
- **No `schemas/` top-level folder.** DTOs live inside the owning module's `contracts/` so other modules import them by name — the reverse of a monolith's "shared schemas" directory.

## Tools config that affects everyone

| File | Controls |
|---|---|
| `pyproject.toml` | Ruff rules, ty config, pytest markers (`asyncio_mode=auto`, `-m 'not e2e'`), SQLModel-related ty-false-positive suppressions |
| `client_app/biome.json` | JS/TS linting + formatting |
| `client_app/vitest.config.ts` | JS unit-test setup |
| `Makefile` | Inner dev loop. If it's not `make <target>`, run the underlying `uv` / `npm` / `alembic` command directly. |

## Host entry points

Both flat and workspace scaffolds use the same framework-owned boot sequence:

```python
from simple_module_hosting.host import build_host_app

app = build_host_app(__file__, routers=("routes:router",))
```

Use router import strings so dotenv is loaded before application imports.
For packaged routes, use their dotted module path (for example `my_app.routes:router`).
Pass `project_root=` for a custom layout; `SM_PROJECT_ROOT` takes precedence.
Keep application-specific mounts after the call, using `app.state.sm.settings`
for development-only conditions. Existing copied entry points remain supported;
replace their common boot code with this call to receive framework upgrades.
See [Settings](/framework/settings) for boot ordering and
[Migrations](/database/migrations) for the matching Alembic entry point.

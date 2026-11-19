# Quickstart

Five minutes from `uv run smpy new` to a running app with a freshly scaffolded module.

## 1. Install the CLI

```bash
uv tool install simple_module_cli
```

(Or `pipx install simple_module_cli`.) That installs the `smpy` executable. Run it through `uv run` to use the app environment. Already installed? `uv tool upgrade simple_module_cli` (or `pipx upgrade simple_module_cli`). A new app pins the framework to the CLI's own version, so an old CLI scaffolds an old app; `uv run smpy new` warns when PyPI has a newer one.

## 2. Scaffold an app

```bash
uv run smpy new myapp --yes
cd myapp
```

`--yes` accepts the defaults (SQLite, no multi-tenancy, the `standard` preset: `auth`, `users`, `dashboard`, `permissions`). The CLI runs `uv sync --all-packages`, `npm install`, and `alembic upgrade heads` for you.

For an interactive run with prompts, drop the `--yes`. For a preset + extras: `uv run smpy new myapp --preset standard --with background_tasks,file_storage --yes`.

## 3. Boot it

```bash
make dev
```

The API and Vite dev servers start side by side. Visit:

- `http://localhost:8000` — landing page
- `http://localhost:8000/users/login` — sign-in screen
- `http://localhost:8000/dashboard` — the authenticated home (log in first)
- `http://localhost:8000/admin` — the admin section overview (log in as an admin; lists whichever admin screens are installed)
- `http://localhost:8000/admin/settings/` — the admin settings UI (log in first; only when the `settings` module is installed, e.g. the `full` preset or `--with settings`)

## 4. Create an admin

Until an administrator exists, every page redirects to the `/setup` wizard, which asks for one. To create it from a terminal instead (from inside `myapp`):

```bash
uv run smpy users create-admin --email admin@example.com
```

It prompts for the password without echoing it. Pick a real one (a passphrase such as `correct-horse-battery-staple` is fine locally); `--password` exists for scripts, but it lands in your shell history.

Sign in at `/users/login` and you land on the dashboard.

## 5. Scaffold a new module

```bash
uv run smpy create-module orders --dest modules/orders
```

This generates a publishable module at `modules/orders/` with a working CRUD sample for one `Order` table:

- `pyproject.toml` — `[project.entry-points.simple_module]` → `orders.module:OrdersModule`
- No frontend config files are needed: the host generates module TypeScript projects. An authored `tsconfig.json` overrides the defaults. Declare extra JS dependencies in an optional dependency-only `package.json` inside the Python package so they ship in wheels; `uv run smpy host sync-js-deps` installs them into the host.
- `orders/module.py` — `ModuleBase` subclass with `meta = ModuleMeta(name="Orders", ...)`: routes, a sidebar menu item and permissions.
- `orders/models.py` — the `Order` table; `orders/contracts/schemas.py` — its DTOs.
- `orders/core/` — `constants.py` (permissions, page keys, menu). Pass `--with-settings` to also get `settings.py` (a `DbBackedSettings` class), `services.py` (stored on `app.state.orders`) and the `register_settings` hook.
- `orders/web/` — the service plus REST endpoints at `/api/orders` and Inertia views at `/orders/`.
- `orders/pages/` — `Browse`, `Create` and `Edit` pages; `orders/locales/en.json` — their strings.
- `tests/` — pytest tests mirroring the areas (`tests/core/…`, `tests/web/crud/…`), with module-prefixed basenames such as `test_orders_crud.py`.

The [first-module guide](/guide/first-module) shows how to grow it: your own fields, validation, a migration and tests.

Inside a workspace app, `create-module` adds the package to `host/pyproject.toml`
as a uv workspace source, runs `uv sync --all-packages` and `npm install` from
the app root, then `uv run smpy gen`. The module's pages and i18n keys are ready.
Running `uv sync` inside `modules/orders` would sync only that module and uninstall
the rest of the app from its shared venv. In a flat app, add the standalone module
with `uv run smpy add ./modules/orders`, then run `make install`.

## 6. Generate a migration

```bash
uv run smpy migrations new orders -m "add orders tables"
make migrate
```

`uv run smpy migrations new orders` selects `orders@head` when the label exists,
or creates the module's first labelled root. Review the generated revision before
applying it. Autogenerate compares every installed module's metadata; check for
unrelated changes. A branch label does not isolate rollbacks: see
[Removing one module's schema](/database/migrations#removing-one-modules-schema).

## 7. Hit the module

Restart `make dev` (modules are discovered at start-up). The reload `make dev` does when files change is not enough: it keeps the import path it started with, so a module installed since then logs "installed but … cannot be imported in this process" until you restart. Then:

```bash
curl -i http://localhost:8000/api/orders
# → 401 {"detail":"Not authenticated"}
```

The scaffold guards every route with the module's `orders.*` permissions, so an anonymous request is refused. Sign in as the admin and visit `http://localhost:8000/orders/` — you see the `Browse` page with an empty list and a "Create" button. The sidebar menu now includes an **Orders** entry (registered via `register_menu_items`).

## 8. Run the tests

```bash
uv run pytest
```

Just the new module, or a single file:

```bash
uv run pytest modules/orders
uv run pytest modules/orders/tests/web/crud/test_orders_crud.py -v
```

The scaffold writes `modules/orders/tests/web/crud/test_orders_crud.py` (REST and page endpoints), `modules/orders/tests/core/module/test_orders_module.py` and `modules/orders/tests/core/contracts/test_orders_schemas.py`.

## What just happened

- **Discovery** — the `simple_module` entry point pointed Python's installer at `orders.module:OrdersModule`. `discover_modules()` loaded it, topologically sorted against every other installed module, and invoked `register_*` hooks in order.
- **Routes** — `register_routes(api_router, view_router)` attached the `orders` routers at `/api/orders` and `/orders`.
- **Menu** — `register_menu_items` pushed an entry onto `MenuRegistry`; the Inertia shared-props middleware serialized it into `menus.sidebar` for every authenticated request.
- **Frontend** — `modules.generated.ts` (rebuilt by `uv run smpy gen`, automatically during install/dev/build) maps `"Orders/Browse"` to `modules/orders/orders/pages/Browse.tsx`. Vite resolves and HMR-watches that file.
- **Database** — `create_module_base("orders")` gave the module its own SQLModel `MetaData` so Alembic can attribute the `orders_order` table to it.

## Next steps

- [Your first module](/guide/first-module) — extend the scaffold into real domain logic, end-to-end.
- [Project structure](/guide/project-structure) — the directory tour, so you know where everything lives.
- [Framework overview](/framework/overview) — what happens between `make dev` and the first HTTP request.
- [Bundled modules](/modules/) — what's already in the box (auth, users, permissions, settings, …).

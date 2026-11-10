# Quickstart

Five minutes from `smpy new` to a running app with a freshly scaffolded module.

## 1. Install the CLI

```bash
uv tool install simple_module_cli
```

(Or `pipx install simple_module_cli`.) That puts `smpy` on your PATH globally.

## 2. Scaffold an app

```bash
smpy new myapp --yes
cd myapp
```

`--yes` accepts the defaults (SQLite, no multi-tenancy, the `standard` preset: `auth`, `users`, `dashboard`, `permissions`). The CLI runs `uv sync`, `npm install`, and `alembic upgrade heads` for you.

For an interactive run with prompts, drop the `--yes`. For a preset + extras: `smpy new myapp --preset standard --with background_tasks,file_storage --yes`.

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
uv run smpy users create-admin --email admin@example.com --password changeme
```

Sign in at `/users/login` and you land on the dashboard.

## 5. Scaffold a new module

```bash
smpy create-module orders --dest modules/orders
smpy add ../modules/orders --path host
```

This generates a publishable module at `modules/orders/` with a working CRUD sample for one `Order` table:

- `pyproject.toml` — `[project.entry-points.simple_module]` → `orders.module:OrdersModule`
- `package.json` + `tsconfig.json` — JS workspace metadata so `tsc --noEmit` covers the module's `.tsx` pages.
- `orders/module.py` — `ModuleBase` subclass with `meta = ModuleMeta(name="Orders", ...)`: settings, routes, a sidebar menu item and permissions.
- `orders/models.py` — the `Order` table; `orders/contracts/schemas.py` — its DTOs.
- `orders/core/` — `constants.py` (permissions, page keys, menu), `settings.py` (a `DbBackedSettings` class) and `services.py` (stored on `app.state.orders`).
- `orders/web/` — the service plus REST endpoints at `/api/orders` and Inertia views at `/orders/`.
- `orders/pages/` — `Browse`, `Create` and `Edit` pages; `orders/locales/en.json` — their strings.
- `tests/` — pytest tests mirroring the areas (`tests/core/…`, `tests/web/crud/…`), with module-prefixed basenames such as `test_orders_crud.py`.

The [first-module guide](/guide/first-module) shows how to grow it: your own fields, validation, a migration and tests.

`smpy add ../modules/orders --path host` adds the package to `host/pyproject.toml` as a uv workspace source and runs `uv sync`, which registers its entry point; the module is discovered on the next boot. In a `smpy new --flat` app the module is not a workspace member, so wire it with `smpy add ./modules/orders` instead.

## 6. Generate a migration

```bash
make migration msg="add orders tables"
make migrate
```

`make migration` runs Alembic from the host directory (where `alembic.ini` lives). Autogenerate picks up the new `orders_*` tables and writes `host/migrations/versions/XXXX_add_orders_tables.py`. Add `branch_labels = ("orders",)` to that revision to give it a named target. The label does not isolate the module: `alembic downgrade orders@base` rolls back the whole chain beneath it. See [Removing one module's schema](/database/migrations#removing-one-modules-schema).

## 7. Hit the module

Restart `make dev` (modules are discovered at boot). Then:

```bash
curl http://localhost:8000/api/orders
# → [] (200)
```

Visit `http://localhost:8000/orders` — you see the `Browse` page with an empty list and a "Create" button. The sidebar menu now includes an **Orders** entry (registered via `register_menu_items`).

## 8. Run the tests

```bash
uv run pytest
```

Single file:

```bash
uv run pytest modules/orders/tests/test_orders.py -v
```

## What just happened

- **Discovery** — the `simple_module` entry point pointed Python's installer at `orders.module:OrdersModule`. `discover_modules()` loaded it, topologically sorted against every other installed module, and invoked `register_*` hooks in order.
- **Routes** — `register_routes(api_router, view_router)` attached the `orders` routers at `/api/orders` and `/orders`.
- **Menu** — `register_menu_items` pushed an entry onto `MenuRegistry`; the Inertia shared-props middleware serialized it into `menus.sidebar` for every authenticated request.
- **Frontend** — `modules.generated.ts` (rebuilt by `make gen-pages`) maps `"Orders/Browse"` to `modules/orders/orders/pages/Browse.tsx`. Vite resolves and HMR-watches that file.
- **Database** — `create_module_base("orders")` gave the module its own SQLModel `MetaData` so Alembic can attribute the `orders_order` table to it.

## Next steps

- [Your first module](/guide/first-module) — extend the scaffold into real domain logic, end-to-end.
- [Project structure](/guide/project-structure) — the directory tour, so you know where everything lives.
- [Framework overview](/framework/overview) — what happens between `make dev` and the first HTTP request.
- [Bundled modules](/modules/) — what's already in the box (auth, users, permissions, settings, …).

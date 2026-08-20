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
- `http://localhost:8000/settings/modules` — the admin settings UI (log in first; only when the `settings` module is installed, e.g. the `full` preset or `--with settings`)

## 4. Create an admin

In another terminal, from inside `myapp`:

```bash
uv run smpy users create-admin --email admin@example.com --password changeme
```

Sign in at `/users/login` and you land on the dashboard.

## 5. Scaffold a new module

```bash
smpy create-module orders --dest modules/orders
uv add ./modules/orders
```

This generates a publishable starter module at `modules/orders/` with:

- `pyproject.toml` — `[project.entry-points.simple_module]` → `orders.module:OrdersModule`
- `package.json` + `tsconfig.json` — JS workspace metadata so `tsc --noEmit` covers the module's `.tsx` pages.
- `orders/module.py` — `ModuleBase` subclass with `meta = ModuleMeta(name="Orders", ...)`, wiring `register_routes` and `register_settings`.
- `orders/services.py` — module-scoped state container (stored on `app.state.orders` by `register_settings`).
- `orders/settings.py` — the module's `pydantic_settings` settings class.
- `orders/endpoints/api.py` — starter REST endpoints at `/api/orders`.
- `orders/pages/` — empty page dir; add `.tsx` pages (and a `register_routes` view router) as you build views.
- `tests/test_orders.py` — pytest smoke test. Named after the package so a repo
  with several modules doesn't collide at collection: without `tests/__init__.py`,
  pytest derives the test module's name from the basename alone.

You add the domain model (`models.py`), DTOs (`contracts/`), service, Inertia views, and pages yourself — the [first-module guide](/guide/first-module) walks through that.

`uv add ./modules/orders` adds the package to your app's dependencies; on the next `uv sync` (which `uv add` also runs) the entry point is registered and the module becomes discoverable on next boot.

## 6. Generate a migration

```bash
make migration msg="add orders tables"
make migrate
```

`make migration` runs Alembic from the host directory (where `alembic.ini` lives). Autogenerate picks up the new `orders_*` tables and writes `host/migrations/versions/XXXX_add_orders_tables.py`. Add `branch_labels = ("orders",)` to that revision so you can later `alembic downgrade orders@base` to roll the module back in isolation.

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

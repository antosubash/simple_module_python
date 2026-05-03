# Quickstart

Five minutes from `git clone` to a running app with a freshly scaffolded module.

## 1. Install

```bash
git clone https://github.com/antosubash/simple_module_python.git
cd simple_module_python
make install
cp .env.example .env
```

## 2. Migrate

```bash
make migrate
```

Default `.env` uses SQLite — no Docker needed. If you want Postgres, run `make docker-up` first and edit `SM_DATABASE_URL` accordingly.

## 3. Boot

```bash
make dev
```

The API and Vite dev servers start side by side. Visit:

- `http://localhost:8000` — landing page
- `http://localhost:8000/users/login` — sign-in screen
- `http://localhost:8000/dashboard` — the authenticated home (log in first)
- `http://localhost:8000/settings/modules` — the admin settings UI (log in first)

## 4. Create an admin

In another terminal:

```bash
uv run sm-users create-admin --email admin@example.com --password changeme
```

Sign in at `/users/login` and you land on the dashboard.

## 5. Scaffold a new module

```bash
make new-module name=orders
```

This generates `modules/orders/` with:

- `pyproject.toml` — `[project.entry-points.simple_module]` → `orders.module:OrdersModule`
- `package.json` + `tsconfig.json` — JS workspace metadata so `tsc --noEmit` covers the module's `.tsx` pages (SM017 warns if these are missing).
- `orders/module.py` — `ModuleBase` subclass with `meta = ModuleMeta(name="Orders", ...)`
- `orders/models.py` — `Order` SQLModel table with `AuditMixin`
- `orders/contracts/schemas.py` — `OrderCreate`, `OrderOut` DTOs
- `orders/service.py` — CRUD implementation
- `orders/services.py` — module-scoped state container (stored on `app.state.orders` by `register_settings`)
- `orders/deps.py` — FastAPI dependencies
- `orders/endpoints/api.py` — REST endpoints at `/api/orders`
- `orders/endpoints/views.py` — Inertia endpoints at `/orders`
- `orders/pages/Browse.tsx`, `Create.tsx`, `Edit.tsx` — React pages
- `orders/locales/en.json` — translation namespace
- `modules/orders/tests/test_orders.py` — pytest smoke test

The scaffolder registers the package and re-runs `uv sync --all-packages`, so the module is discoverable on next boot.

## 6. Generate a migration

```bash
make migration msg="add orders tables"
make migrate
```

Alembic's autogenerate picks up the new `orders` schema (Postgres) or the `orders_*` tables (SQLite) and writes `host/migrations/versions/XXXX_add_orders_tables.py`. The first migration of a new module includes a `branch_labels = ("orders",)` marker so you can downgrade the module in isolation later with `alembic downgrade orders@base`.

## 7. Hit the module

Restart `make dev` (modules are discovered at boot). Then:

```bash
curl http://localhost:8000/api/orders
# → [] (200)
```

Visit `http://localhost:8000/orders` — you see the `Browse` page with an empty list and a "Create" button. The sidebar menu now includes an **Orders** entry (registered via `register_menu_items`).

## 8. Run the tests

```bash
make test
```

Runs Python + JS test suites. Single file:

```bash
uv run pytest modules/orders/tests/test_api.py -v
```

## What just happened

- **Discovery** — the `simple_module` entry point pointed Python's installer at `orders.module:OrdersModule`. `discover_modules()` loaded it, topologically sorted against every other installed module, and invoked `register_*` hooks in order.
- **Routes** — `register_routes(api_router, view_router)` attached the `orders` routers at `/api/orders` and `/orders`.
- **Menu** — `register_menu_items` pushed an entry onto `MenuRegistry`; the Inertia shared-props middleware serialized it into `menus.sidebar` for every authenticated request.
- **Frontend** — `modules.generated.ts` (rebuilt by `make gen-pages`) maps `"Orders/Browse"` to `modules/orders/orders/pages/Browse.tsx`. Vite resolves and HMR-watches that file.
- **Database** — `create_module_base("orders")` namespaced the `Order` table under a Postgres `orders` schema (or the `orders_order` table name under SQLite).

Where to go next:

- [Your first module](/guide/first-module) — stage-by-stage walk-through extending the scaffold to real domain logic.
- [Framework overview](/framework/overview) — what actually happens between `make dev` and the first HTTP request.
- [Project structure](/guide/project-structure) — the directory tour.

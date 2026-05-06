# Quickstart

Five minutes from `sm new` to a running app with a freshly scaffolded module.

## 1. Install the CLI

```bash
uv tool install simple_module_cli
```

(Or `pipx install simple_module_cli`.) That puts `sm` on your PATH globally.

## 2. Scaffold an app

```bash
sm new myapp --yes
cd myapp
```

`--yes` accepts the defaults (SQLite, no multi-tenancy, the `standard` preset: `auth`, `users`, `permissions`, `dashboard`, `settings`, `feature_flags`). The CLI runs `uv sync`, `npm install`, and `alembic upgrade head` for you.

For an interactive run with prompts, drop the `--yes`. For a preset + extras: `sm new myapp --preset standard --with background_tasks,file_storage --yes`.

## 3. Boot it

```bash
make dev
```

The API and Vite dev servers start side by side. Visit:

- `http://localhost:8000` — landing page
- `http://localhost:8000/users/login` — sign-in screen
- `http://localhost:8000/dashboard` — the authenticated home (log in first)
- `http://localhost:8000/settings/modules` — the admin settings UI (log in first)

## 4. Create an admin

In another terminal, from inside `myapp`:

```bash
uv run sm-users create-admin --email admin@example.com --password changeme
```

Sign in at `/users/login` and you land on the dashboard.

## 5. Scaffold a new module

```bash
sm create-module orders --dest modules/orders
uv add ./modules/orders
```

This generates `modules/orders/` with:

- `pyproject.toml` — `[project.entry-points.simple_module]` → `orders.module:OrdersModule`
- `package.json` + `tsconfig.json` — JS workspace metadata so `tsc --noEmit` covers the module's `.tsx` pages.
- `orders/module.py` — `ModuleBase` subclass with `meta = ModuleMeta(name="Orders", ...)`.
- `orders/models.py` — `Order` SQLModel table with `AuditMixin`.
- `orders/contracts/schemas.py` — `OrderCreate`, `OrderOut` DTOs.
- `orders/service.py` — CRUD implementation.
- `orders/services.py` — module-scoped state container (stored on `app.state.orders` by `register_settings`).
- `orders/deps.py` — FastAPI dependencies.
- `orders/endpoints/api.py` — REST endpoints at `/api/orders`.
- `orders/endpoints/views.py` — Inertia endpoints at `/orders`.
- `orders/pages/Browse.tsx`, `Create.tsx`, `Edit.tsx` — React pages.
- `orders/locales/en.json` — translation namespace.
- `tests/test_orders.py` — pytest smoke test.

`uv add ./modules/orders` adds the package to your app's dependencies; on the next `uv sync` (which `uv add` also runs) the entry point is registered and the module becomes discoverable on next boot.

## 6. Generate a migration

```bash
uv run alembic revision --autogenerate -m "add orders tables"
make migrate
```

Alembic's autogenerate picks up the new `orders` schema (Postgres) or the `orders_*` tables (SQLite) and writes `migrations/versions/XXXX_add_orders_tables.py`. Add `branch_labels = ("orders",)` to that revision so you can later `alembic downgrade orders@base` to roll the module back in isolation.

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
- **Database** — `create_module_base("orders")` namespaced the `Order` table under a Postgres `orders` schema (or the `orders_order` table name under SQLite).

## Next steps

- [Your first module](/guide/first-module) — extend the scaffold into real domain logic, end-to-end.
- [Project structure](/guide/project-structure) — the directory tour, so you know where everything lives.
- [Framework overview](/framework/overview) — what happens between `make dev` and the first HTTP request.
- [Bundled modules](/modules/) — what's already in the box (auth, users, permissions, settings, …).

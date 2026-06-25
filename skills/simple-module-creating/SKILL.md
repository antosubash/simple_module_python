---
name: simple-module-creating
description: Use when adding a new feature package to a simple_module_python app. Triggers on "create a new module", "add a module", "scaffold a feature", or when an empty module directory under modules/ needs to be filled in.
---

# Creating a simple_module_python module

**Always scaffold with the generator. Never hand-roll the directory.**

## Quick path

```bash
# scaffold a module into this repo's modules/orders/ — also wires the package
# into host/ + root pyproject.toml and runs `uv sync --all-packages`
make new-module name=orders

# if you added a frontend page, regenerate the Inertia manifest
make gen-pages

# if you added SQLModel tables, autogenerate + apply a migration
make migration msg="add orders module"
make migrate
```

`make new-module` (→ `scripts/new_module.py`) is the in-repo path and produces
the full tree below. For a **standalone publishable package** (its own repo,
with CI + PyPI `publish.yml`), use `smpy create-module orders` instead — a
leaner scaffold; pass `--standalone` to force the `.github/` workflows, then
`uv sync` (or `pip install -e ./orders`) to install it into the host.

## What scaffolding produces

```
modules/orders/
├── pyproject.toml          # entry point declared here
├── package.json            # per-module JS deps
├── tsconfig.json
├── tests/test_orders.py
└── orders/
    ├── module.py           # OrdersModule(ModuleBase) with ModuleMeta
    ├── models.py           # Base = create_module_base("orders")
    ├── contracts/schemas.py # SQLModel DTOs — public surface
    ├── service.py          # business logic
    ├── services.py         # app.state.orders state container (settings)
    ├── settings.py         # SM_ORDERS_* env → dataclass
    ├── deps.py             # FastAPI dependencies
    ├── endpoints/{api,views}.py
    ├── pages/{Browse,Create,Edit}.tsx  # *.tsx, auto-discovered by Vite
    └── locales/en.json
```

`make new-module` also edits `host/pyproject.toml` (adds the workspace dep) and
the root `pyproject.toml` (type-check + test paths), so the module is picked up
by the host and by `make lint`/`make test` without further wiring.

## The contract: pyproject.toml + module.py

The host discovers modules via a single entry point. If this is wrong, the module silently does nothing in dev and **fails boot in production** (strict discovery).

```toml
# modules/orders/pyproject.toml
[project]
name = "simple_module_orders"
version = "0.1.0"
requires-python = ">=3.12"

[project.entry-points.simple_module]
orders = "orders.module:OrdersModule"
```

```python
# modules/orders/orders/module.py
from simple_module_core.module import ModuleBase, ModuleMeta

class OrdersModule(ModuleBase):
    meta = ModuleMeta(
        name="Orders",                    # PascalCase, must be unique
        route_prefix="/api/orders",
        view_prefix="/orders",
        depends_on=[],                    # other module names (PascalCase)
    )
```

`ModuleMeta.name` is load-bearing in two places: the `__tablename__` prefix you author and the PascalCase Inertia component namespace. So directory `blog_posts` → `name="BlogPosts"` → `inertia.render("BlogPosts/Index", ...)` → `pages/Index.tsx`. Mismatches fire diagnostic codes `SM003` (orphan page) / `SM004` (phantom render).

`ModuleMeta` also accepts `version=` (defaults to `"1.0.0"`) and `requires_framework=` (a PEP 440 spec for the framework API range, e.g. `">=1.0,<2.0"`) so the host can reject incompatible installs at boot — set these on modules you intend to publish.

## Lifecycle hooks (override only what you need)

In execution order — all no-op by default:

| Hook | Use it for |
|---|---|
| `register_settings(app)` | Read `SM_<MODULE>_*` env into a dataclass on `app.state.<lower_name>` |
| `register_menu_items(registry)` | Sidebar / navbar entries |
| `register_permissions(registry)` | `<module>.<action>` strings, grouped |
| `register_feature_flags(registry)` | `FeatureFlagDefinition` constants |
| `register_event_handlers(bus)` | `bus.subscribe(EventCls, handler)` |
| `register_health_checks(registry)` | Module-owned health probes |
| `register_public_routes(registry)` | Exempt routes from auth via `add_prefix` / `add_regex` (method-aware) |
| `register_exception_handlers(app)` | Module-specific error mapping |
| `register_middleware(app)` | LIFO — module middleware sorted last wraps outermost |
| `register_routes(api_router, view_router)` | `include_router(...)` your two routers |
| `on_startup(app)` / `on_shutdown(app)` | Async; shutdown runs in reverse order |

## Verify after scaffolding

Boot the host. Diagnostics run automatically: in development, warnings/errors land in the boot logs; in production (`SM_ENVIRONMENT != development`), errors fail the boot. Codes `SM001`/`SM008`/`SM009` are blocking; `SM007` (module overrides no hooks) is info-only.

The new module should appear in the registered-modules log line. If it has a view endpoint, visit `<view_prefix>/`. Run `make doctor` for the same diagnostics out of band (orphan pages, coupling, migration drift, locale checks) — see the **simple-module-doctor** skill for the full code list.

## Pitfalls

- **Forgot the entry point.** Package installs, module silently doesn't load (production strict mode raises `InvalidModuleError`). Verify `[project.entry-points.simple_module]` exists in `pyproject.toml`.
- **`name=` collides.** Two modules with the same `ModuleMeta.name` raise `SM008` at boot.
- **Registered the module by hand in host code.** Don't — discovery is entry-point-only; host code never imports module code.

For framework-wide rules that apply once the module exists (SQLModel-everywhere, file-size cap, settings layout, no `session.commit()` in services), see the **simple-module-conventions** skill. For migration mechanics see **simple-module-migrations**.

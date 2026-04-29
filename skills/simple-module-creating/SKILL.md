---
name: simple-module-creating
description: Use when adding a new feature package to a simple_module_python app. Triggers on "create a new module", "add a module", "scaffold a feature", or when an empty module directory under modules/ needs to be filled in.
---

# Creating a simple_module_python module

**Always scaffold with the generator. Never hand-roll the directory.**

## Quick path

```bash
# scaffold a publishable module package in ./orders (run in a fresh repo or
# inside a host's modules/ directory)
sm create-module orders

# install the new package into the host environment
uv sync   # or: pip install -e ./orders

# if you added a frontend page, regenerate the Inertia manifest
sm host gen-pages --host-dir=client_app

# if you added SQLModel tables, autogenerate + apply a migration
uv run alembic revision --autogenerate -m "add orders module"
uv run alembic upgrade head
```

## What scaffolding produces

```
orders/
├── pyproject.toml          # entry point declared here
└── orders/
    ├── module.py           # OrdersModule(ModuleBase) with ModuleMeta
    ├── models.py           # Base = create_module_base("orders")
    ├── contracts/          # SQLModel DTOs — public surface
    ├── endpoints/{api,views}.py
    ├── pages/              # *.tsx, auto-discovered by Vite
    └── locales/en.json
```

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
from simple_module_core import ModuleBase, ModuleMeta

class OrdersModule(ModuleBase):
    meta = ModuleMeta(
        name="Orders",                    # PascalCase, must be unique
        route_prefix="/api/orders",
        view_prefix="/orders",
        depends_on=[],                    # other module names (PascalCase)
        version="0.1.0",
    )
```

`ModuleMeta.name` is load-bearing in three places: the Postgres schema name, the SQLite `__tablename__` prefix you author, and the PascalCase Inertia component namespace. So directory `blog_posts` → `name="BlogPosts"` → `inertia.render("BlogPosts/Index", ...)` → `pages/Index.tsx`. Mismatches fire diagnostic codes `SM003` (orphan page) / `SM004` (phantom render).

For modules you intend to publish, also add `version=` (your module's semver) and `requires_framework=` (a PEP 440 spec for the framework API range, e.g. `">=1.0,<2.0"`) so the host can reject incompatible installs at boot.

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
| `register_exception_handlers(app)` | Module-specific error mapping |
| `register_middleware(app)` | LIFO — module middleware sorted last wraps outermost |
| `register_routes(api_router, view_router)` | `include_router(...)` your two routers |
| `on_startup(app)` / `on_shutdown(app)` | Async; shutdown runs in reverse order |

## Verify after scaffolding

Boot the host. Diagnostics run automatically: in development, warnings/errors land in the boot logs; in production (`SM_ENVIRONMENT != development`), errors fail the boot. Codes `SM001`/`SM008`/`SM009` are blocking; `SM007` (module overrides no hooks) is info-only.

The new module should appear in the registered-modules log line. If it has a view endpoint, visit `<view_prefix>/`.

## Pitfalls

- **Forgot the entry point.** Package installs, module silently doesn't load (production strict mode raises `InvalidModuleError`). Verify `[project.entry-points.simple_module]` exists in `pyproject.toml`.
- **`name=` collides.** Two modules with the same `ModuleMeta.name` raise `SM008` at boot.
- **Registered the module by hand in host code.** Don't — discovery is entry-point-only; host code never imports module code.

For framework-wide rules that apply once the module exists (SQLModel-everywhere, file-size cap, settings layout, no `session.commit()` in services), see the **simple-module-conventions** skill. For migration mechanics see **simple-module-migrations**.

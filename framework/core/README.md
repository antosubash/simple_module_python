# simple-module-core

Module-system primitives for the [simple_module](https://github.com/antosubash/simple_module_python) framework — a modular-monolith for Python/FastAPI where each feature is a plugin package discovered at boot.

This package defines `ModuleBase`, the `ModuleMeta` descriptor, the `discover_modules()` entry-point loader, topological dependency sorting, event bus primitives, and the diagnostic codes (`SM001`–`SM017`) used by `make doctor`.

## Install

```bash
pip install simple-module-core
```

You usually don't install this directly — it's pulled in by `simple-module-hosting` and every `simple-module-*` module.

## What it provides

- `ModuleBase` — the subclass every module extends to opt into lifecycle hooks.
- `ModuleMeta` — required `meta = ModuleMeta(name=..., depends_on=...)` attribute on each module.
- `discover_modules()` — loads all `[project.entry-points.simple_module]` modules, topologically sorts by `depends_on`.
- Diagnostic registry — `SM001` missing meta, `SM003` orphan page, `SM008` duplicate name, `SM009` framework→plugin coupling violation, and ~ten others.
- Tiny event-bus (`pyee`) for decoupled module-to-module communication.

## Usage

```python
# modules/orders/orders/module.py
from simple_module_core import ModuleBase, ModuleMeta


class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders", depends_on=["users"])

    def register_routes(self, api_router, view_router):
        from .endpoints import api, views
        api_router.include_router(api.router)
        view_router.include_router(views.router)
```

And in `pyproject.toml`:

```toml
[project.entry-points.simple_module]
orders = "orders.module:OrdersModule"
```

The host's `discover_modules()` call picks this up automatically at boot.

## Depends on

- `fastapi`, `pydantic`, `pydantic-settings`, `pyee`, `babel`, `packaging`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

# simple_module_settings

Runtime settings UI for [simple_module](https://github.com/antosubash/simple_module_python) apps. Other modules plug their own settings panels into a shared admin view — one page per module tab — without the host having to know about them.

## Install

```bash
pip install simple_module_settings
```

## What it provides

- `/settings` admin page (and `/settings/modules`) aggregating every installed module's settings into one editable view.
- `register_module_settings(app, package, SettingsClass, services_factory)` helper — a module calls this from its own `register_settings(app)` hook to record its `BaseSettings` class; the UI renders its fields automatically (no panel/page wiring needed).
- DB-backed runtime settings store (hydrated into each module's `BaseSettings` at startup, before module `on_startup` hooks run) for values admins change at runtime.

## Usage

Register a module's settings from its `register_settings(app)` hook:

```python
from fastapi import FastAPI


class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders")

    def register_settings(self, app: FastAPI) -> None:
        from simple_module_core.module_settings import register_module_settings
        from orders.settings import OrdersSettings
        from orders.services import OrdersServices

        register_module_settings(
            app, "orders", OrdersSettings, lambda s: OrdersServices(settings=s)
        )
```

That surfaces the module's settings fields under `/admin/settings/`, hydrated from the DB store at startup. The settings class is normally a `simple_module_core.settings_base.DbBackedSettings` (DB is the only source). Registration and hydration live in the framework (#500); this module adds the admin editor, hot reload and the key/value API. `settings.registration`, `settings.module_registry` and `settings.hydrate` are deprecated re-exports.

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

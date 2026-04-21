# simple_module_settings

Runtime settings UI for [simple_module](https://github.com/antosubash/simple_module_python) apps. Other modules plug their own settings panels into a shared admin view — one page per module tab — without the host having to know about them.

## Install

```bash
pip install simple_module_settings
```

## What it provides

- `/settings` admin page aggregating every installed module's settings panel.
- `register_settings_panel()` hook — a module declares `{title, inertia_page, requires_permission}`; `simple_module_settings` renders the tab.
- DB-backed runtime settings table (separate from env-var-driven `SM_*` settings) for values admins change at runtime.

## Usage

Register a panel:

```python
class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders")

    def register_settings_panel(self):
        return {
            "title": "Orders",
            "inertia_page": "Orders/SettingsPanel",
            "requires_permission": "orders.manage",
        }
```

That adds an **Orders** tab at `/settings`. The rendered page is a regular Inertia page authored inside the `orders` module.

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

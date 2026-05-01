# simple_module_dashboard

Admin landing page + sidebar menu host for authenticated users of a [simple_module](https://github.com/antosubash/simple_module_python) app. Renders `/dashboard`, collects menu entries registered by every other installed module, and provides the primary Inertia layout.

Pre-wired into any app scaffolded with `simple-module new`.

## Install

```bash
pip install simple_module_dashboard
```

## What it provides

- `/dashboard` Inertia view, a single entry point for logged-in users.
- Global sidebar renderer — aggregates `register_menu_items()` calls from all modules into one tree.
- Breadcrumb + page-title provider used by downstream module pages.

## Usage

Install the module in a host, and any other module can register a menu entry:

```python
# modules/orders/orders/module.py
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.menus import MenuItem


class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders")

    def register_menu_items(self):
        return [MenuItem(label="Orders", href="/orders", icon="shopping-bag")]
```

The dashboard sidebar picks it up automatically.

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`
- `simple_module_users` (user counts shown on the default layout)

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

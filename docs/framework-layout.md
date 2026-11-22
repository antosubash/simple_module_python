# Framework layout

Every package under `framework/` (`core`, `db`, `hosting`, `inertia`, `testing`, `cli`) follows this area layout alongside [Module layout](module-layout.md).

The goal is the same: find code by asking which subsystem owns it, while keeping top-level package imports (`simple_module_db`, `simple_module_core`, `simple_module_hosting`, `simple_module_inertia`, `simple_module_test`) and external submodule imports stable across a two-release deprecation window.

## Package directory

```text
framework/<project>/
├── <package>/       Python package organized into domain areas
├── tests/           Python tests mirroring package areas
├── tests-js/        Vitest tests, when present (hosting)
├── README.md, LICENSE, pyproject.toml
```

## Package root: lookup & wire paths

Only entries resolved by packaging metadata, CLI entry points, resource lookups, frozen outbox wire names, active deprecation shims, and declared domain area directories belong at the package root:

| Package | Allowed root entries (besides `__init__.py`, `py.typed`, areas, shims) | Reason |
| --- | --- | --- |
| `simple_module_core` | `__main__.py`, `tenant_events.py`, `user_events.py` | CLI diagnostics entry point; frozen durable outbox event wire names pinned by `host/tests/test_durable_wire_names.py` |
| `simple_module_db` | — | Everything groups into domain areas; `tenant_cleanup` handler keeps its wire name via explicit `subscribe_durable(..., name=...)` |
| `simple_module_hosting` | `__main__.py`, `host_cli.py`, `admin_overview/`, `setup_wizard/`, `locales/`, `ui_locales/` | Host CLI entry point and discovery/package-data subpackages |
| `simple_module_inertia` | — | Package root re-exports top-level public API; internals live in areas |
| `simple_module_test` | `plugin.py` | `pytest11` entry point registered in `framework/testing/pyproject.toml` |
| `simple_module_cli` | `cli.py`, `migration_recipes/`, `templates/`, `skills` | `smpy` / `simple-module` script entry point, `simple_module.data_upgrades` entry points, and package data |

## Domain areas per package

An area's `__init__.py` holds only a docstring, except explicit public facade packages such as `framework/core/simple_module_core/diagnostics/`. Private helpers keep a leading underscore inside the area they serve. Every source module must import cleanly in a fresh Python interpreter (`python -c "import <pkg>.<mod>"`). The 300-line file cap applies to framework sources and tests.

- **`framework/inertia` (`simple_module_inertia`):** `protocol`, `rendering`, `assets`
- **`framework/cli` (`simple_module_cli`):** `commands`, `scaffold`, `sources`, `updates`, `tooling`, `migrations`
- **`framework/core` (`simple_module_core`):** `modules`, `access`, `events`, `settings`, `web`, `i18n`, `mail`, `runtime`, `diagnostics`, `migrations`
- **`framework/db` (`simple_module_db`):** `engine`, `models`, `scopes`, `audit`, `migrations`, `queries`
- **`framework/hosting` (`simple_module_hosting`):** `boot`, `settings`, `middleware`, `rate_limit`, `auth`, `errors`, `frontend`, `i18n`, `observability`, `leases`
- **`framework/testing` (`simple_module_test`):** `app`, `db`, `web`, `fakes`

```text
framework/<project>/tests/
├── conftest.py                 # shared package fixtures (plus root _*_support.py / _*_models.py helpers)
├── <area>/test_*.py            # mirrored area tests (or <area>/<feature>/test_*.py for large areas)
```

Test directories contain no `__init__.py` and no flat `tests/test_*.py` files; pytest's `--import-mode=importlib` allows repeated test basenames across areas. Shared root test helper directories remain listed under `[tool.pytest.ini_options].pythonpath` in `pyproject.toml`.

## Compatibility shims for moved paths

Any old framework submodule path imported outside its owning package (in `modules/`, `host/`, or downstream `smpy_modules`) keeps a `sys.modules` alias shim at the old root location with `remove_in="0.0.52"` (`docs/framework/deprecations.md`):

- Packages that depend on `simple_module_core` (`core`, `db`, `hosting`, `testing`) use `simple_module_core.deprecation.deprecated_module`.
- Leaf packages (`inertia`, `cli`) keep zero dependency on `core` by emitting stdlib `DeprecationWarning` before aliasing `sys.modules[__name__]` and registering the expiry target directly in `host/tests/test_deprecation_expiry.py`.

`host/tests/test_framework_layout.py` enforces this contract per package once removed from `LEGACY_FLAT`. `host/tests/test_deprecation_expiry.py` auto-discovers active framework alias shims and fails once the framework reaches `remove_in`.

## Migration status

| Package | Source dir | Root `.py` (target excludes shims) | Flat `tests/test_*.py` | State |
| --- | --- | ---: | ---: | --- |
| `inertia` | `simple_module_inertia` | 16 | 23 | legacy flat (`LEGACY_FLAT`) |
| `cli` | `simple_module_cli` | 46 | 83 | legacy flat (`LEGACY_FLAT`) |
| `core` | `simple_module_core` | 71 | 79 | legacy flat (`LEGACY_FLAT`) |
| `db` | `simple_module_db` | 56 | 78 | legacy flat (`LEGACY_FLAT`) |
| `hosting` | `simple_module_hosting` | 109 | 177 | legacy flat (`LEGACY_FLAT`) |
| `testing` | `simple_module_test` | 22 | 14 | legacy flat (`LEGACY_FLAT`) |

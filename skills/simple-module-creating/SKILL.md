---
name: simple-module-creating
description: Use when adding a new feature package to a simple_module_python app. Triggers on "create a new module", "add a module", "scaffold a feature", or when an empty module directory under modules/ needs to be filled in.
---

# Creating a simple_module_python module

**Always scaffold with the generator. Never hand-roll the directory.**

## Quick path

```bash
# scaffold a module into this repo's modules/orders/ — also wires the package
# into host/ + root pyproject.toml + the release matrix, then runs
# `uv sync --all-packages`, `npm install` and `make gen-i18n`
make new-module name=orders

# if you added a frontend page, regenerate the Inertia manifest
make gen-pages

# if you added SQLModel tables, autogenerate + apply a migration
make migration msg="add orders module"
make migrate
```

`make new-module` (→ `scripts/new_module.py`) is the in-repo path. It calls the
same `create_module` as `smpy create-module`, so both produce the same tree
below (permissions, menu item with `label_key`, `core/constants.py`, CRUD sample,
`locales/en.json`); the in-repo variant adds workspace-sourced `pyproject.toml`
metadata and a `LICENSE`. The pages read their text from `locales/en.json`
through `t(keys.<module>.…)`; the host's `make gen-i18n` (also run by
`make install` and each dev boot) adds the module to `keys`. A `--standalone`
module repo gets pages with literal English instead, since it has no host to
generate `keys`. For a **standalone publishable
package** (its own repo, with CI + PyPI `publish.yml`), use
`smpy create-module orders`; pass `--standalone` to force the `.github/`
workflows, then `uv sync` (or `pip install -e ./orders`) to install it into the
host. Inside a `smpy new` app, `smpy create-module orders --dest modules/orders`
makes a workspace member and prints the app's steps (`smpy add … --path host`,
`make install`, `make migration`); don't run `uv sync` inside the module there.

Settings are omitted by default. Add `--with-settings` to `smpy create-module`
or `ARGS=--with-settings` to `make new-module` only when the module needs
DB-backed configuration. This adds the settings class, services container and
`register_settings` hook. Inertia pages are bundled by the host; module releases
need no page prebundling.

Ordinary modules need no frontend config files. The host generates TypeScript
configs; an authored tsconfig.json remains an override. For extra JS dependencies,
add a dependency-only package.json inside the Python package so it ships in wheels,
and run `smpy host sync-js-deps`. Root manifests remain npm workspace overrides.

## What scaffolding produces

```text
modules/orders/
├── pyproject.toml
├── orders/
│   ├── __init__.py, py.typed, module.py
│   ├── models.py                 # or models/; discovered by name
│   ├── contracts/                # public SQLModel DTOs and extension contracts
│   ├── core/                     # constants.py; settings/services only with --with-settings
│   ├── web/                      # deps.py, service.py (or services/), private schemas
│   │   └── endpoints/            # api.py, views.py
│   ├── pages/                    # Inertia pages, api.ts, api.generated.ts
│   ├── locales/                  # <lang>.json
│   ├── ui/                       # components/, hooks/, utils/ (when needed)
│   └── tasks.py, theme.css, styles.css  # optional root lookup files
└── tests/
    ├── conftest.py                # module-wide fixtures
    ├── core/module/test_orders_module.py
    ├── core/contracts/test_orders_schemas.py
    └── web/crud/test_orders_crud.py
```

`make new-module` also edits `host/pyproject.toml` (adds the workspace dep), the
root `pyproject.toml` (type-check + test paths) and the `publish-pypi` matrix in
`release.yml`, so the module is picked up by the host and by `make lint`/`make
test` without further wiring. Commit the `uv.lock`, `package-lock.json` and
regenerated i18n key files it leaves behind.

Modules use this area layout.
Area initializers hold only a docstring. Private helpers stay in their area.
Tests have no `__init__.py` and keep `conftest.py` at their root. The test plugin
defaults to importlib mode, so test basenames may repeat; JS tests stay in `tests-js/`.
See [Module layout](https://docs.py.simplemodule.dev/module-layout) for the lookup consumers and shim policy.

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
        name="Orders",  # PascalCase, must be unique
        route_prefix="/api/orders",
        view_prefix="/orders",
        depends_on=[],  # modules this one needs (PascalCase); missing → prod boot fails
        optional_depends_on=[],  # ordering only: sort after these when loaded
    )
```

`ModuleMeta.name` is the PascalCase Inertia component and dependency identity.
The Python package name owns table prefixes and the default i18n namespace.
So directory `blog_posts` → `name="BlogPosts"` →
`inertia.render("BlogPosts/Index", ...)` → `pages/Index.tsx`. Mismatches fire
diagnostic codes `SM003` (orphan page) / `SM004` (phantom render).

`route_prefix` and `view_prefix` both default to `""`, preserving existing
absolute route paths. Declare prefixes explicitly; scaffolds use dash-separated
URLs such as `/api/blog-posts` and `/blog-posts`. Keep existing prefix values
when adopting conventional routers so URLs do not change.
During discovery, the version defaults to the distribution owning the entry
point, including editable installs. Outside discovery it stays `"1.0.0"`;
explicit `version=` wins. Discovery replaces the instance's frozen metadata
without changing the class. Set `requires_framework=`
to a PEP 440 framework API range (e.g. `">=1.0,<2.0"`) for published modules.
`locale_dirs()` discovers `<package>/locales` using the lowercase last package
component as namespace (`acme.billing` uses `billing`);
override only for custom directories/namespaces or to opt out.

## Lifecycle hooks (override only what you need)

In execution order — no-op by default except conventional router discovery:

| Hook | Use it for |
|---|---|
| `register_settings(app)` | `register_module_settings(app, "<pkg>", SettingsCls, factory)` (from `simple_module_core.module_settings`): DB-hydrated settings on `app.state.<lower_name>` |
| `register_menu_items(registry)` | Sidebar / navbar entries |
| `register_permissions(registry)` | `<module>.<action>` strings, grouped |
| `register_feature_flags(registry)` | `FeatureFlagDefinition` constants |
| `register_event_handlers(bus)` | `bus.subscribe(EventCls, handler)` |
| `register_health_checks(registry)` | Module-owned health probes |
| `register_public_routes(registry)` | Exempt routes from auth via `add_prefix` / `add_regex` (method-aware) |
| `register_cors_policies(registry)` | Opt a public, cross-origin path into CORS (`registry.add_regex(pattern, CorsPolicy(...), enabled=...)`); most specific match wins |
| `register_csp_sources(registry)` | Whitelist external asset origins in the CSP (`registry.add("style-src", "https://rsms.me")`) — fetch directives only, validated at boot |
| `register_exception_handlers(app)` | Module-specific error mapping |
| `register_middleware(app)` | LIFO — module middleware sorted last wraps outermost |
| `register_routes(api_router, view_router)` | Default includes `<package>.web.endpoints.api.router` and `.views.router` when present; override for custom layouts or ordering. Existing module import errors propagate. The host applies prefixes and tags once. |
| `on_startup(app)` / `on_shutdown(app)` | Async; shutdown runs in reverse order |

## Verify after scaffolding

Boot the host. The diagnostics pass runs **only in development** — warnings/errors print to the boot logs and any ERROR raises `SystemExit`. In **production** the diagnostics pass is skipped; the one thing that fails a production boot is strict module *discovery* (a bad entry point — broken import, missing `meta`, non-`ModuleBase` class), surfaced as `SM001`. So `SM008`/`SM009` are dev-boot / `make doctor` errors, not production-boot blockers; `SM007` (module overrides no hooks) is info-only.

The new module should appear in the registered-modules log line. If it has a view endpoint, visit `<view_prefix>/`. Run `make doctor` for the same diagnostics out of band (orphan pages, coupling, migration drift, locale checks) — see the **simple-module-doctor** skill for the full code list.

## Pitfalls

- **Forgot the entry point.** Package installs, module silently doesn't load (production strict mode raises `InvalidModuleError`). Verify `[project.entry-points.simple_module]` exists in `pyproject.toml`.
- **`name=` collides.** Two modules with the same `ModuleMeta.name` raise `SM008` at dev boot / `make doctor` (their lowercased names would also collide as table prefixes in the shared schema).
- **Registered the module by hand in host code.** Don't — discovery is entry-point-only; host code never imports module code.

Services raise domain exceptions derived from a per-module base in
`core/errors.py`, never `HTTPException`. Map them in endpoints or
`register_exception_handlers(app)` (as in `file_storage`); translate at the
request boundary. Preserve existing status codes, JSON bodies and headers.
Endpoint-level `HTTPException` for pure request validation remains fine.

For framework-wide rules that apply once the module exists (SQLModel-everywhere, file-size cap, settings layout, no `session.commit()` in services), see the **simple-module-conventions** skill. For migration mechanics see **simple-module-migrations**.

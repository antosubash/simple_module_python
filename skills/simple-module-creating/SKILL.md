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

# refresh all generated frontend artifacts (also automatic on install/dev/build)
make gen

# if you added SQLModel tables, autogenerate + apply a migration
make migration msg="add orders module"
make migrate
```

`make new-module` (→ `scripts/new_module.py`) is the in-repo path. It calls the
same `create_module` as `uv run smpy create-module`, so both produce the same tree
below (permissions, menu item with `label_key`, `core/constants.py`, CRUD sample,
`locales/en.json`); the in-repo variant adds workspace-sourced `pyproject.toml`
metadata and a `LICENSE`. The pages read their text from `locales/en.json`
through `t(keys.<module>.…)`; the host's `make gen-i18n` (also run by
`make install` and each dev boot) adds the module to `keys`. A `--standalone`
module repo gets pages with literal English instead, since it has no host to
generate `keys`. For a **standalone publishable
package** (its own repo, with CI + PyPI `publish.yml`), use
`uv run smpy create-module orders`; pass `--standalone` to force the `.github/`
workflows, then `uv sync` (or `pip install -e ./orders`) to install it into the
host. Inside a `uv run smpy new` app, `uv run smpy create-module orders --dest modules/orders`
wires the workspace member into its host, syncs Python/npm dependencies and runs
`uv run smpy gen`. Its next step is `uv run smpy migrations new orders -m "init"`,
then `make migrate` and a dev restart; do not sync from inside the module.

Settings are omitted by default. Add `--with-settings` to `uv run smpy create-module`
or `ARGS=--with-settings` to `make new-module` only when the module needs
DB-backed configuration. This adds the settings class, services container and
`register_settings` hook. Inertia pages are bundled by the host; module releases
need no page prebundling.

Ordinary modules need no frontend config files. The host generates TypeScript
configs; an authored tsconfig.json remains an override. For extra JS dependencies,
add a dependency-only package.json inside the Python package so it ships in wheels,
and run `uv run smpy host sync-js-deps`. Root manifests remain npm workspace overrides.

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
│   ├── pages/                    # Inertia pages, generated API client + types
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

Declare admin routing once with `ModuleMeta(admin=AdminSurface(prefix="/admin/orders",
routes="orders.admin.views:router", menu_group="Access",
menu_group_key="ui.nav_groups.access"))` (import `AdminSurface` from
`simple_module_core`). It defaults this module's menu URLs below the prefix to
`ADMIN_SIDEBAR` and its pages to `AdminLayout` after `make gen-pages`. Explicit
menu/layout choices win. It grants no permissions; guard routes and menu items.
Omitted `routes` loads `<package>.web.endpoints.admin:router`; hook overrides win.

## Lifecycle hooks (override only what you need)

In execution order — defaults discover conventional routers and register `ModuleBase.permissions`:

| Hook | Use it for |
|---|---|
| `register_settings(app)` | `register_module_settings(app, "<pkg>", SettingsCls, factory)` (from `simple_module_core.module_settings`): DB-hydrated settings on `app.state.<lower_name>` |
| `register_menu_items(registry)` | Sidebar / navbar entries |
| `register_permissions(registry)` | Defaults to the `PermissionCatalogue` on `permissions`; overrides extend with `super()` |
| `register_feature_flags(registry)` | `FeatureFlagDefinition` constants |
| `register_event_handlers(bus, app)` | `bus.subscribe(EventCls, handler)` |
| `register_health_checks(registry)` | Module-owned health probes |
| `register_public_routes(registry)` | Exempt routes from auth via `add_prefix` / `add_regex` (method-aware) |
| `register_cors_policies(registry)` | Opt a public, cross-origin path into CORS (`registry.add_regex(pattern, CorsPolicy(...), enabled=...)`); most specific match wins |
| `register_csp_sources(registry)` | Whitelist external asset origins in the CSP (`registry.add("style-src", "https://rsms.me")`) — fetch directives only, validated at boot |
| `register_exception_handlers(app)` | Module-specific error mapping |
| `register_middleware(app)` | LIFO — module middleware sorted last wraps outermost |
| `register_routes(api_router, view_router)` | Default includes `<package>.web.endpoints.api.router` and `.views.router` when present; override for custom layouts or ordering. Existing module import errors propagate. The host applies prefixes and tags once. |
| `register_admin_routes(admin_router)` | Defaults to the router in `meta.admin = AdminSurface(...)`; legacy `admin_view_prefix` + overrides remain supported. |
| `register_fallback_routes(router)` | Opt-in catch-all views at `view_prefix`. Finalized at startup and before first dispatch after ordinary routes and mounts, including post-builder host additions and bare mount redirects. Dependency order; first match wins. Fallback-only views retain discovery order for login destinations. Auth/tenant middleware and opt-in CSRF still apply; public access uses `register_public_routes`. |
| `on_startup(app)` / `on_shutdown(app)` | Async; shutdown runs in reverse order |

Move catch-alls out of the conventional views router into the fallback hook.
Pass host routers through `create_app(..., routers=(host_router,))` or
`build_host_app(..., routers=(host_router,))` so they precede fallbacks;
routers or custom mounts added to the returned app are appended afterward.
Use dependencies to order overlapping fallback modules; a matched handler's 404
does not try the next fallback. See `docs/framework/lifecycle.md`.

## Verify after scaffolding

Boot the host. The diagnostics pass runs **only in development** — warnings/errors print to the boot logs and any ERROR raises `SystemExit`. In **production** the static pass is skipped; strict discovery rejects broken entry points/missing metadata (`SM001`), duplicate meta names (`SM008`, naming both distributions) and missing dependencies (`SM030`). Auth-provider selection and migration checks also run outside development. Lenient discovery warns on duplicates and skips later entries. `SM009` remains a dev-boot / `make doctor` check; `SM007` (module overrides no hooks) is info-only.

Auth modules declare `ModuleMeta(provides_auth=True)` for selection and SM020/SM021.
The old `_is_auth_provider` module marker warns once per class and is removed in
0.1.0. SM020 warns on undeclared module objects exposing the provider protocol
shape; separate provider objects created inside hooks are not statically detectable.

`SM_MODULES_ENABLED` accepts JSON lists of meta names or explicit
`ep:<entry_point_name>` selectors, case-insensitively. To exclude a broken plugin
before import, every list item must use `ep:` (for example `ep:background_tasks`).
Unqualified items always match metadata names; mixed lists load all candidates
before matching. Unknown explicit selectors fail strict discovery and warn in
development. Entry points sort by distribution name, entry-point name and target,
so development keeps a deterministic duplicate winner. See `docs/framework/discovery.md`.

The new module should appear in the registered-modules log line. If it has a view endpoint, visit `<view_prefix>/`. Run `make doctor` for the same diagnostics out of band (orphan pages, coupling, migration drift, locale checks) — see the **simple-module-doctor** skill for the full code list.

## Pitfalls

- **Forgot the entry point.** Package installs, module silently doesn't load (production strict mode raises `InvalidModuleError`). Verify `[project.entry-points.simple_module]` exists in `pyproject.toml`.
- **`name=` collides.** Duplicate `ModuleMeta.name` values raise `InvalidModuleError` with `SM008` in strict discovery; development warns and skips the later entry point. Rename or disable one. Static diagnostics also reject table-prefix collisions in their supplied module list.
- **Registered the module by hand in host code.** Don't — discovery is entry-point-only; host code never imports module code.

Services raise domain exceptions derived from a per-module base in
`core/errors.py`, never `HTTPException`. Map them in endpoints or
`register_exception_handlers(app)` (as in `file_storage`); translate at the
request boundary. Preserve existing status codes, JSON bodies and headers.
Endpoint-level `HTTPException` for pure request validation remains fine.

For framework-wide rules that apply once the module exists (SQLModel-everywhere, file-size cap, settings layout, no `session.commit()` in services), see the **simple-module-conventions** skill. For migration mechanics see **simple-module-migrations**.

# Module layout

Every module under `modules/` uses this layout; the last one moved in #862.
A downstream module still on the flat layout moves as described in
[Moving an existing module](#moving-an-existing-module).
The downstream `smpy_modules` layout is the reference for areas; this repo
keeps its own pytest naming and collection conventions.

The aim is to find code by asking which feature it belongs to. A small module
needs only `core/` and `web/`; do not create empty domain areas for future work.

## Module directory

```text
modules/<name>/
  <package>/       Python package and frontend sources
  tests/           Python tests mirroring package areas
  tests-js/        Vitest tests, when needed
  docs/            module-specific documentation, when needed
  README.md, LICENSE, pyproject.toml, package.json, tsconfig.json
```

## Package root: lookup paths

Only files looked up by name and the area directories belong at the root.
Consumer locations below refer to this repository; Python imports are resolved
by the interpreter, while `py.typed` is the PEP 561 marker for external type
checkers, not a framework runtime lookup.

| Root entry | Consumer (file:line) and reason |
| --- | --- |
| `__init__.py` | Python package import; `framework/hosting/simple_module_hosting/assets.py:117` uses `importlib.resources.files(pkg_name)` to find it. |
| `py.typed` | PEP 561 consumers; `framework/cli/simple_module_cli/templates/module/pyproject.toml.tpl:33` selects the whole package for the wheel, including this marker. |
| `module.py` | `framework/core/simple_module_core/discovery.py:80` loads the `simple_module` entry point; the scaffold declares its target in `framework/cli/simple_module_cli/templates/module/pyproject.toml.tpl:15`. |
| `models.py` or `models/` | `framework/db/simple_module_db/migrations.py:74` imports the module's models for metadata; `framework/core/simple_module_core/diagnostics/_tenancy.py:94` and `framework/core/simple_module_core/diagnostics/_expression_index.py:52` do the same. A `models/` package must load its tables. |
| `tasks.py` | `modules/background_tasks/background_tasks/worker/celery_app.py:215` autodiscovers with `related_name="tasks"`; `framework/core/simple_module_core/diagnostics/_heavy_task_imports.py:65` checks this root file (SM028). |
| `task_config.py` | `modules/background_tasks/background_tasks/worker/task_routing.py:46` imports `<package>.task_config` for a module's Celery routes and beat schedule. |
| `contracts/` | Public imports for sibling modules; the scaffold consumer is `framework/cli/simple_module_cli/templates/module/__PACKAGE__/web/service.py.tpl:15`. Keep public SQLModel DTOs, events and real extension contracts here. |
| `pages/` | `framework/hosting/simple_module_hosting/manifest.py:97` discovers pages; `framework/hosting/simple_module_hosting/page_globs.py:34` emits their Vite glob; `framework/core/simple_module_core/diagnostics/_pages.py:170` checks page names. |
| `pages/api.ts`, `pages/api.generated.ts` | `framework/cli/simple_module_cli/openapi_types.py:130` selects the root pages directory for generation; `framework/cli/simple_module_cli/templates/module/__PACKAGE__/pages/api.ts.tpl:8` consumes the generated types. |
| `locales/` | The scaffold's `framework/cli/simple_module_cli/templates/module/__PACKAGE__/module.py.tpl:88` resolves the root directory in `locale_dirs()`; `framework/core/simple_module_core/module.py:210` documents the hook contract. |
| `theme.css`, `styles.css` | `framework/hosting/simple_module_hosting/assets.py:126` discovers both; `framework/core/simple_module_core/diagnostics/_css.py:171` and `framework/core/simple_module_core/diagnostics/_css.py:193` check their different cascade rules (SM022/SM023). |
| `cli.py` | Only when a declared entry point targets it: `framework/cli/simple_module_cli/plugins.py:41` loads CLI plugins. |

Other root files and folders are legacy exceptions, tracked explicitly by
`host/tests/test_module_layout.py:1`. Keep named lookup paths pinned with tests
that load them as their consumer does. Generated wheel metadata such as
`package.json` is packaging output, not another source area.

## Areas

| Area | Holds |
| --- | --- |
| `core/` | `constants.py`, `errors.py`, `settings.py` (the `DbBackedSettings` subclass), `services.py` (the `app.state.<pkg>` container), events and cross-cutting helpers. |
| `web/` | `endpoints/{api,views}.py`, `deps.py`, CSRF, private request schemas, and `service.py` or `services/` for reads and writes endpoints share. |
| One folder per domain subject | Only for a subject with several features of its own; for example `ingest/` with uploads and imports. |
| `ui/` | Frontend components, hooks and utilities that are not Inertia pages. |

Choose an area by ownership:

- Used by most features: `core/`. A helper used by two features belongs to
  the closest owning feature rather than automatically becoming core.
- Part of answering an HTTP request: `web/`.
- Otherwise: the domain subject it implements. One feature does not need a
  new root area; put it in the nearest existing area.

An area's `__init__.py` holds only a docstring. Public exports belong in
`contracts/`, not area initializers. Private helpers live in the package they
serve with a leading underscore, such as `web/_validation.py`.
Every Python module must import in a fresh interpreter. Break import cycles
at the ownership boundary; when a call-time import is necessary, explain why.
The 300-line cap still applies, including tests; split by responsibility.

The root ratchet permits `core/`, `web/`, `ui/` and the lookup paths above.
Declare a new multi-feature domain area in its `DOMAIN_AREAS` map when needed.

## Frontend

| Path | Holds |
| --- | --- |
| `pages/` | Real Inertia pages, plus `api.ts` and `api.generated.ts`. Keep page names and render keys stable. |
| `ui/components/<feature>/` | Reusable components grouped by feature. Shared components may sit directly in `ui/components/`. |
| `ui/hooks/`, `ui/utils/` | Hooks and plain TypeScript helpers. |
| `modules/<name>/tests-js/` | All new JS tests and their support; Vitest collects here. |

Tailwind scans `ui/`, pages and legacy root `components/` on wheel-installed
modules, including nested source directories hidden by a venv's ignore file.
The asset manifest exposes `ui`; the pages manifest still contains only
`pages/`. Biome covers `ui/**`; the untranslated-string and double-cast checks
already recurse throughout the package. Module tsconfig includes recurse too.
Both host and scaffold `client_app/module-assets.ts` readers also register UI
source prefixes for Vite's bare-import fallback and dependency scan. Existing
hosts must update that reader when adopting UI sources; upgrading Python
packages regenerates manifests but does not rewrite host-owned Vite config.
Wheel templates include UI sources and exclude `**/*.test.*`, `**/*.spec.*`,
`**/test-dom.tsx` and `**/page-tests/**` so old frontend test helpers do not
ship. `make ci-build-packages` fails when any built wheel (this repo's own modules included) still contains a JS or TS test file,
`test-dom.tsx` or a `page-tests/` directory (`scripts/check_wheel_contents.py`).
Keep CSS tokens in root `theme.css` and component rules in root `styles.css`.

The separate legacy `smpy module build` command still uses root `assets_src/`
and `static/dist/`. PR 0 preserves that contract and the optional scaffold
`static_mounts()` hook; neither directory exists in a fresh scaffold. These
roots are not added to the new layout's allowed set. Migrating that bundler,
or adopting it in a new in-repo module, needs a separate layout policy change;
normal Inertia pages and `ui/` sources use the host's build pipeline.

## Tests

```text
tests/
  conftest.py
  core/module/test_orders_module.py
  core/contracts/test_orders_schemas.py
  web/crud/test_orders_crud.py
  <area>/<feature>/test_orders_<feature>.py
```

Mirror package ownership, using `tests/<area>/<feature>/test_<module>_*.py`.
Keep module-wide `conftest.py` at `tests/` root. Do not add `__init__.py` in test
directories. Basenames must be globally unique: default pytest import mode
loads non-package tests by basename, even when they live in different folders.
The root-layout test refuses a `test_*.py` directly under `tests/`.

A helper shared by several test folders stays at `tests/` root as
`_<module>_support.py`. The root `conftest.py` puts that directory on
`sys.path`, so `from _<module>_support import ...` keeps working from nested
folders; a module that has helpers needs that `conftest.py` even when it holds
no fixtures.

The root `pyproject.toml:137` lists `modules/<name>/tests` in `testpaths`, and
`framework/cli/simple_module_cli/framework_repo.py` wires that root. Pytest
recursively collects nested areas without listing each child directory.
JS tests stay in `tests-js/`, not in package `ui/`.

## Compatibility for move PRs

Inventory old import paths used outside the module, both in this repository
and downstream. Every such old path becomes a shim using
`simple_module_core.deprecation.deprecated_module`, with `remove_in="0.0.46"`.
Update internal imports to the new path; do not make new code depend on shims.
A shim built as the `sys.modules` alias below is discovered automatically by
`host/tests/test_deprecation_expiry.py` (`_layout_shims()`), so it needs no manual
registration. The expiry test fails once the installed framework reaches the removal release.
See [Deprecations](framework/deprecations.md) for the API.

For example, after moving `orders.service` to `orders.web.service`, leave this
at `orders/service.py` if external callers use that old path:

```python
"""Moved to :mod:`orders.web.service`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("orders.service", remove_in="0.0.46", use="orders.web.service")
sys.modules[__name__] = importlib.import_module("orders.web.service")
```

The alias makes both paths the same module object, so mocks and
`monkeypatch` strings keep working. Files containing both `deprecated_module(`
and `sys.modules[__name__]` are auto-discovered by the expiry test and ignored
by the root-layout test while they remain. When the old path was inside a
package that moved (for example `orders.endpoints.api`), keep that package with a docstring-only `__init__.py`
and alias each module in it; a package holding only aliases is ignored by the
root-layout test too. A shim that is a plain re-export instead (not an alias) must be added
by hand to the expiry test's `_SHIM_MODULES` tuple and `_EXPECTED` set and to
the root-layout test's `DEPRECATED_ROOT` map until removed.

## Downstream modules

A module created with `smpy create-module` already follows this layout. The
check that keeps it that way lives in this repo's
[`host/tests/test_module_layout.py`](https://github.com/antosubash/simple_module_python/blob/main/host/tests/test_module_layout.py),
which an app or a standalone module repo does not have. To keep the same ratchet:

1. Copy that test into your own tests, for example `tests/test_module_layout.py`. <!-- path-check: ignore -->
2. Point `MODULES` at your modules directory (`modules/` in a `smpy new` app).
3. Replace `DOMAIN_AREAS` with your own modules' named areas, and empty
   `DEPRECATED_ROOT` unless you keep root-level shims.

`ALLOWED_ROOT` is the root lookup list in [Package root](#package-root-lookup-paths);
keep the two in step when you upgrade the framework.

## Moving an existing module

One module per PR; no logic changes in a move PR.

1. **Pin first.** Test root lookup paths through their actual discovery
   consumer, public contracts, page render keys and task names. Inventory
   imports in this repo and downstream before changing any paths.
2. **Move with a script.** Use `git mv` and rewrite imports, including
   `from <pkg> import x`, `mock.patch` targets and `monkeypatch` dotted strings.
   Rewrite relative TS imports from their old location. Do not rewrite
   `app.state.<pkg>` attributes: these are runtime containers, not imports.
   Do not rewrite strings that only look like paths: i18n keys
   (`<pkg>.audit.token`), permission names and upgrade ids share the prefix.
   Durable event keys and handler names are wire names derived from the
   import path: a moved durable handler keeps its old name with
   `subscribe_durable(..., name=<constant>)`, and a moved durable event class
   needs a data migration. `host/tests/test_durable_wire_names.py` freezes both.
3. Move tests to matching areas/features, keep root `conftest.py`, remove test
   package initializers and prefix each basename with the module name.
   JS tests remain in `tests-js/`.
4. Add external-import shims with removal release `0.0.46`, alias shims are
   auto-discovered by the expiry test (re-export shims are registered by hand),
   drop the shim's `DEPRECATED_ROOT` entry once it expires, and update the
   status table below. Domain areas must be named in `DOMAIN_AREAS`.
5. Run `python -c "import <pkg>.<mod>"` in a **fresh interpreter for every
   module**, not one interpreter importing all modules in sequence.
6. Run the module suite plus `host/tests`, `make lint`, and `make doctor`.
   Exercise its browser specs where present. Where tasks exist, start a Celery
   worker and check registration under the unchanged task names.
7. Review the diff as moves and import rewrites only. Verify wheel contents,
   UI scanning and module lookup paths. Keep logic changes in another PR.

## Migration status (2026-11-05)

Counts refer to the source package root and direct `tests/test_*.py` files;
cache directories are ignored. Shim files left at old paths are counted separately. Update this table
when a later module PR moves files.

| Module | Root `.py` files | Flat `tests/test_*.py` | State |
| --- | ---: | ---: | --- |
| api_tokens | 3 (+4 shims) | 0 | follows this layout |
| audit_log | 3 | 0 | follows this layout |
| auth | 3 (+4 shims) | 0 | follows this layout |
| background_tasks | 4 (+10 shims) | 0 | follows this layout |
| branding | 2 (+6 shims) | 0 | follows this layout |
| dashboard | 2 | 0 | follows this layout |
| feature_flags | 3 (+1 shim) | 0 | follows this layout |
| file_storage | 4 (+7 shims) | 0 | follows this layout |
| keycloak | 3 (+5 shims) | 0 | follows this layout |
| mail | 2 (+2 shims) | 0 | follows this layout |
| oidc | 3 (+3 shims) | 0 | follows this layout |
| permissions | 3 (+2 shims) | 0 | follows this layout |
| settings | 4 (+8 shims, +3 deprecated re-exports) | 0 | follows this layout |
| sharing | 3 (+3 shims) | 0 | follows this layout |
| site_lock | 2 (+1 shim) | 0 | follows this layout |
| tenants | 3 (+6 shims) | 0 | follows this layout |
| users | 3 (+7 shims) | 0 | follows this layout |

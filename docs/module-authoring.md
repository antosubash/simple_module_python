# Module authoring guide

This is the reference for authoring a module that is installable from PyPI
and assembled into a host by the `smpy create-host` scaffold. It describes the
contract a module must follow, the env-var conventions, the migration
workflow the host developer uses, and the API-version / semver rules.

## Anatomy of a module package

```text
my-module/
├── pyproject.toml                  # declares entry point + framework dep
├── my_module/
│   ├── __init__.py
│   ├── module.py                   # ModuleBase subclass
│   ├── models.py                   # SQLModel tables (optional)
│   ├── endpoints/                  # FastAPI routes
│   ├── pages/                      # Inertia TSX pages (optional)
│   ├── templates/                  # Jinja2 templates (optional)
│   ├── static/dist/                # pre-built frontend assets (optional)
│   ├── contracts/schemas.py        # SQLModel DTOs — the public surface
│   └── contracts/events.py         # domain events (optional)
└── tests/
```

### Standalone vs in-repo: `.github/` workflows

`smpy create-module` ships a `.github/` with `ci.yml` + `publish.yml` (PyPI
trusted-publishing on a `v*` tag) — useful when the module lives in its **own
repo**. When you scaffold a module **inside an existing repo/host** (the
documented `modules/*` monorepo layout), the CLI omits `.github/` by default:
GitHub only runs workflows from the repository-root `.github/workflows/`, so a
nested per-module one never runs, and `publish.yml` would be a publish footgun.
Pass `--standalone` to force the workflows for a module destined for its own
repo. See GH #210.

### Service types: concrete class, not Protocol

Export the concrete service class from `<module>.service` and have consumers
type-hint against it. Do **not** ship a `contracts/service.py` with an
`IFooService` Protocol by default — it's dead boilerplate when there's only
one implementation.

Add a Protocol only when the module is a real extension point with multiple
interchangeable implementations that an operator can swap at runtime. The
canonical example is `file_storage.StorageBackend`: it has a registry, two
shipped implementations (`FilesystemBackend`, `S3Backend`), and tests that
mock against the Protocol. If none of those apply to your module, skip it.

### Minimal `pyproject.toml`

```toml
[project]
name = "simple_module_my_module"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "simple_module_core>=1.0,<2.0",
  "simple_module_db>=1.0,<2.0",
  "simple_module_hosting>=1.0,<2.0",
]

[project.entry-points.simple_module]
my_module = "my_module.module:MyModule"
```

### Minimal `module.py`

```python
from simple_module_core import ModuleBase, ModuleMeta


class MyModule(ModuleBase):
    meta = ModuleMeta(
        name="MyModule",
        route_prefix="/api/my-module",
        view_prefix="/my-module",
        depends_on=[],  # other module names
        version="0.1.0",  # your module's semver
        requires_framework=">=1.0,<2.0",  # framework API range
    )
```

## API stability contract

`simple_module_core` exposes `FRAMEWORK_API_VERSION` (PEP 440 string). At
boot the host rejects any installed module whose
`Meta.requires_framework` spec does not accept the current framework
version, raising `FrameworkVersionError` with the offending modules named.

**Public surface** (breaking changes bump the major version):

- `ModuleBase`, `ModuleMeta`, and every `register_*` hook signature
- All `*Registry` classes (`MenuRegistry`, `PermissionRegistry`,
  `FeatureFlagRegistry`, `HealthRegistry`)
- `EventBus.publish`, `.publish_nowait`, `.subscribe`
- `create_module_base`, `build_module_metadata`, `make_include_object`
- Model mixins: `AuditMixin`, `SoftDeleteMixin`, `MultiTenantMixin`,
  `VersionedMixin`
- `create_app()` entry point (`simple_module_hosting`)

**Internal** (free to change without bumping major):

- `app_builder._phase_*` helpers and middleware ordering
- Discovery internals beyond the `discover_modules()` signature
- Inertia plumbing
- Logging format

## Feature flags

Declare flags as module-level constants so every consumer imports the
same object instead of retyping the string name, then register them in
`register_feature_flags`. All the helpers are tenant-aware: they read
`request.state.tenant_id` (populated by `TenantMiddleware`) and resolve
tenant override > system override > definition default. They accept
either a `FeatureFlagDefinition` (preferred) or the raw name.

```python
# my_module/constants.py
from simple_module_core import FeatureFlagDefinition

FLAG_BULK_IMPORT = FeatureFlagDefinition(
    name="my_module.bulk_import",
    description="Enable CSV bulk import",
    default_enabled=False,
)
```

```python
# module.py
from simple_module_core import FeatureFlagRegistry, ModuleBase

from my_module.constants import FLAG_BULK_IMPORT


class MyModule(ModuleBase):
    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        registry.add(FLAG_BULK_IMPORT)
```

```python
# endpoints/api.py — four ways to consume, all accept the constant directly
from typing import Annotated
from fastapi import APIRouter, Depends, Request
from simple_module_core import feature_flag, flag_enabled, is_flag_enabled, require_flag

from my_module.constants import FLAG_BULK_IMPORT

router = APIRouter()

# 1. Attribute-style decorator — 404 when off
@router.post("/bulk")
@feature_flag(FLAG_BULK_IMPORT)
async def bulk_import(request: Request, payload: BulkPayload): ...

# 2. FastAPI dependency — 404 when off
@router.post("/bulk-alt", dependencies=[Depends(require_flag(FLAG_BULK_IMPORT))])
async def bulk_import_alt(...): ...

# 3. Inject the value into your handler
@router.get("/")
async def list_items(
    bulk_on: Annotated[bool, Depends(flag_enabled(FLAG_BULK_IMPORT))],
):
    if bulk_on: ...

# 4. Check ad-hoc inside any handler that already has Request
@router.get("/dashboard")
async def dashboard(request: Request):
    if is_flag_enabled(request, FLAG_BULK_IMPORT): ...
```

The `@feature_flag(...)` decorator requires the handler to declare a
`request: Request` parameter (FastAPI injects it automatically) so the
gate can read the tenant context; decorating a handler without one
raises `TypeError` at import time.

Outside of an HTTP request (background tasks, CLI), pass the registry and
tenant explicitly: `registry.is_enabled(FLAG_BULK_IMPORT.name, tenant_id=tenant)`.

## Settings

Each module's settings are loaded via its `register_settings(app)` hook.
Convention: read environment variables under the prefix `SM_<MODULE>_`
(e.g. `SM_AUTH_CLIENT_ID`) and store the result on a module-owned object at
`app.state.<module_package_lower>` (e.g. `app.state.auth`, `app.state.users`).
The `SM012` diagnostic looks for exactly that attribute, so the `_settings`
suffix some older modules used is not recognised. Hosts can declare
`SM_MODULES_ENABLED='["Auth","MyModule"]'` to load only a subset of
installed modules.

## Migrations workflow

Migrations live **in the host scaffold** (`<host>/migrations/versions/`),
not inside the module package. The module ships its SQLModel tables only;
the host developer generates a migration each time a new module is
installed or a module's models change:

```bash
pip install simple_module_my_module
alembic revision --autogenerate -m "add my-module"
# review the generated file
alembic upgrade head
```

The host's `env.py` (scaffolded from the framework's template) calls:

```python
from simple_module_db import build_module_metadata, make_include_object

target_metadata = build_module_metadata()  # every installed module
include_object = make_include_object(target_metadata)
```

`build_module_metadata()` imports each installed module's `<pkg>.models`
submodule via `importlib` — the same mechanism works for editable installs
and pip-installed wheels, so the flow does not change when moving from
local development to production.

`make_include_object(metadata)` returns an Alembic `include_object` filter
that allowlists only tables owned by installed modules. Any host-defined
table (e.g. a user table the host dev added directly) is preserved
untouched by autogenerate.

### Multi-module branches

Each module's first revision should set a `branch_labels` tuple matching
the module name:

```python
# migrations/versions/<id>_initial_my_module.py
branch_labels = ("my_module",)
```

This lets operators roll back a single module's schema with
`alembic downgrade my_module@base` without touching other modules.

## Frontend assets

Modules may ship TSX pages in `my_module/pages/*.tsx`. On host boot (and on
`make gen-pages`) the framework emits:

- `client_app/modules.manifest.json` — machine-readable paths
- `client_app/modules.generated.ts` — per-module `import.meta.glob`
  calls with absolute paths resolved via `importlib.resources`
- `client_app/modules.generated.css` — Tailwind `@source` entries, plus an
  `@import` per module-shipped stylesheet (see [Styling](#styling))
- `client_app/modules.assets.json` — the per-module asset record that
  `vite.config.ts` builds its `#module/<pkg>` aliases from

Vite's `server.fs.allow` is extended to cover each installed module's
package root, so pages shipped inside a wheel work for the dev server and
production build alike.

**Inertia pages never need pre-bundling.** The consuming host's Vite build
compiles `pages/*.tsx` straight out of the installed wheel (via the
`#module/<pkg>` aliases + `server.fs.allow`). `static/dist/` +
`static_mounts()` exist only for assets *outside* that pipeline — vendor JS,
standalone widgets, images. Build them with `smpy module build` (see
[Developing out-of-tree](#developing-out-of-tree)) and expose them via
`ModuleBase.static_mounts()`:

```python
from importlib.resources import files


class MyModule(ModuleBase):
    def static_mounts(self):
        root = files("my_module")
        return {"/modules/my-module/static": root / "static" / "dist"}
```

The host mounts each entry as `StaticFiles` during boot.

## Styling

A module may ship two optional stylesheets beside its `pages/` directory.
Both are auto-detected exactly the way `pages/` is — there is no hook to
override and nothing to register:

```
my_module/
├── module.py
├── theme.css     # optional — @theme tokens, @custom-variant, @font-face
├── styles.css    # optional — component rules, keyframes, vendor CSS
└── pages/
```

`smpy host gen-pages` emits an `@import` for each into
`client_app/modules.generated.css`:

```css
@import "#module/my_module/theme.css";
@import "#module/my_module/styles.css" layer(components);
```

**Nothing needs to be added to the host's `styles.css` by hand.** The
`#module/<pkg>` specifier is a Vite alias built from `modules.assets.json`,
so it resolves identically whether the module is a workspace member or
installed from a wheel — and no generated file ends up containing a
`../../../.venv/lib/python3.12/site-packages/...` path that would break the
next time the interpreter version changes.

Imports are emitted in module discovery order, which is topological by
`ModuleMeta.depends_on`. A module that depends on another can therefore
override its dependency's styles.

### Which file does what

The split is not cosmetic — it is what makes the cascade rules structural
rather than merely documented.

| | `theme.css` | `styles.css` |
|---|---|---|
| Imported | unlayered | `layer(components)` |
| For | `@theme`, `@custom-variant`, `@utility`, `@font-face`, `:root` tokens | component rules, keyframes, vendor CSS |
| Beats a Tailwind utility? | yes | no |

Tailwind v4 expands `@import "tailwindcss"` into
`@layer theme, base, components, utilities`, and **unlayered CSS beats every
layered rule**. So a module shipping a bare `.card { padding: 0 }` unlayered
would silently override `p-4` on that element. But `@theme` blocks *must* be
unlayered to register design tokens at all — a `@theme` inside a layer is
inert. One file cannot satisfy both constraints, so each file gets one job.

`make doctor` catches the two ways to get this wrong: **SM022** flags
`@theme`/`@custom-variant`/`@utility` sitting in `styles.css` (where they do
nothing), and **SM023** flags an unlayered rule in `theme.css` (where it
outranks every utility). Both are warnings — the CSS is legal either way, it
just cascades in a way you probably did not intend.

### Cascade order

```
design-system @theme  <  module theme.css  <  app @theme overrides
```

A module normally *adds* tokens (`--color-map-water`); when it deliberately
redefines a design-system token it wins, and the consuming app still has the
final word from its own `@theme` block below the generated import.

### Packaging

**No packaging change is required.** The module wheel template already
declares `[tool.hatch.build.targets.wheel] packages = ["my_module"]`, and
Hatch includes every file under the package directory — `.css` along with
`.tsx`. Only two extras need declaring: `package.json` lives *outside* the
package dir (a `force-include` maps it in), and `static/dist` is gitignored
(an `artifacts` entry ships it when present without failing the build when
it isn't).

## Developing out-of-tree

A module in its own repo has no host around it — these are the three
commands that close the gap. All of them run from the module repo root.

### Type-checking

`smpy create-module` scaffolds a `package.json` whose devDependencies pin
`@simple-module-py/ui`, `@simple-module-py/tsconfig` and
`@simple-module-py/i18n` to the framework version that created the module
(all three are published to npm in lockstep with the PyPI packages), and a
`tsconfig.json` that resolves `@simple-module-py/ui/*` from your own
`node_modules`. So:

```bash
npm install          # once; commit package-lock.json and use `npm ci` in CI
npm run typecheck    # tsc --noEmit over your pages
```

### `smpy module verify` — does my frontend actually build?

`tsc` alone cannot tell you whether your pages and `theme.css`/`styles.css`
survive a real host build (Vite import resolution, Tailwind scanning, the
`#module/<pkg>` alias plumbing). `verify` answers that by scaffolding a
throwaway host into `.smpy/verify-host/` (cached, gitignored), installing
your module into it as an editable path dependency, and running the host's
real `gen-pages` + `npm run build`:

```bash
uv run smpy module verify          # warm re-runs reuse the cached host
uv run smpy module verify --fresh  # nuke and rebuild the cached host
```

The scaffolded CI workflow runs it on every push. The verify host pins the
framework version you develop against, so a green verify ≈ your module
building inside a freshly scaffolded host of that version. It needs `uv`,
`npm`, and network access to PyPI + npm on first run.

### `smpy module build` — static_mounts() assets

If (and only if) your module ships assets outside the Inertia page pipeline,
put an entry file at `<pkg>/assets_src/index.ts` and run:

```bash
uv run smpy module build
```

It bundles `assets_src/` into `<pkg>/static/dist/` (IIFE, via the verify
host's Vite toolchain — your repo needs no bundler devDependency). The
scaffolded `pyproject.toml` already ships `static/dist` in the wheel via a
hatch `artifacts` entry; the command warns if that entry has been removed.

## Templates

Jinja2 template directories contributed via `ModuleBase.template_dirs()`
are appended to the host's template search path. The host's own
`host/templates/` is searched first so hosts can override module
templates by copying + editing.

## Testing during development

Install `simple_module_test` as a dev dependency (the `smpy create-module`
scaffold does this automatically):

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "simple_module_test>=0.1,<1.0",
]
```

The package registers pytest fixtures via a `pytest11` entry_point — no
`conftest.py` is needed in your module repo. Available fixtures:

| Fixture | What it gives you |
|---|---|
| `build_test_app` | Callable `(ModuleCls) -> FastAPI` — wraps a single module in a minimal FastAPI app with its routes registered. |
| `fake_event_bus` | A `FakeEventBus` that records every `publish`/`publish_nowait` call so tests can assert emitted events. |
| `settings` | In-memory-SQLite `Settings` (`multi_tenant=True`) for the test app. |
| `db_state` / `engine` / `db_session` | Fresh in-memory `DatabaseState` per test; `db_session` creates every installed module's tables and stamps `alembic_version` at head. |
| `app` | A full `create_app(settings)` with lifespan started/stopped. |
| `client` | `httpx.AsyncClient` bound to the test app (anonymous). |
| `authenticated_client` | Same, with a seeded admin + signed session cookie. Requires the `users` module installed (seeds via `users.bootstrap`). |

Example test:

```python
from my_feature.module import MyFeatureModule


async def test_api_emits_event(build_test_app, fake_event_bus):
    app = build_test_app(MyFeatureModule)
    # ... exercise the route via httpx.AsyncClient ...
    fake_event_bus.assert_published(MyFeatureCreated)
```

`FakeEventBus` subclasses the real `EventBus`, so subscribers you wire up
still fire — recording is additive. This means behaviour your tests cover
against the fake behaves identically when the module runs inside a real
host.

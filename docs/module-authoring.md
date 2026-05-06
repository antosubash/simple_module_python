# Module authoring guide

This is the reference for authoring a module that is installable from PyPI
and assembled into a host by the `sm create-host` scaffold. It describes the
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
        depends_on=[],                   # other module names
        version="0.1.0",                 # your module's semver
        requires_framework=">=1.0,<2.0", # framework API range
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
- `build_app()` entry point

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
(e.g. `SM_AUTH_CLIENT_ID`) and store the result on
`app.state.<module_name_lower>_settings`. Hosts can declare
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

target_metadata = build_module_metadata()      # every installed module
include_object  = make_include_object(target_metadata)
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

Vite's `server.fs.allow` is extended to cover each installed module's
package root, so pages shipped inside a wheel work for the dev server and
production build alike.

For production builds, ship a pre-bundled `my_module/static/dist/` inside
the wheel and expose it via `ModuleBase.static_mounts()`:

```python
from importlib.resources import files

class MyModule(ModuleBase):
    def static_mounts(self):
        root = files("my_module")
        return {"/modules/my-module/static": root / "static" / "dist"}
```

The host mounts each entry as `StaticFiles` during boot.

## Templates

Jinja2 template directories contributed via `ModuleBase.template_dirs()`
are appended to the host's template search path. The host's own
`host/templates/` is searched first so hosts can override module
templates by copying + editing.

## Testing during development

Install `simple_module_test` as a dev dependency (the `sm create-module`
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

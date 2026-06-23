# Discovery & entry points

Modules are **Python packages** registered via the `simple_module` entry-point group. There is no module registry file, no `INSTALLED_MODULES` list in settings — if the package is installed in the environment and declares the entry point, it's a module.

## Declaring a module

Every module's `pyproject.toml` ends with:

```toml
[project.entry-points.simple_module]
orders = "orders.module:OrdersModule"
```

- The **key** (`orders`) is the entry-point name. It's used for reporting only — the framework authoritative name is `ModuleMeta.name`.
- The **value** is `<import_path>:<class_name>`. The class must inherit from `simple_module_core.module.ModuleBase` and declare a non-null `meta = ModuleMeta(...)` class attribute.

Entry points are registered **at install time**, not at import time. After editing a module's `pyproject.toml`, re-run `uv sync --all-packages` (or `make install`) so the installer writes the new metadata to the venv's `*.dist-info/entry_points.txt`.

## Discovery algorithm

`simple_module_core.discovery.discover_modules()`:

1. Iterates `importlib.metadata.entry_points(group="simple_module")`.
2. For each entry point, calls `.load()` to import the module's `module.py` and pull out the class, then instantiates it (`module_cls()`).
3. Validates: the loaded object must be a `ModuleBase` subclass with a `meta` attribute of type `ModuleMeta`.
4. If `SM_MODULES_ENABLED` is set, filters to only the modules whose `ModuleMeta.name` (case-insensitive) appears in the list.
5. Returns a `list` of `ModuleBase` **instances** (one per module, constructed with no args). A separate `topological_sort()` call (made by `create_app`) then orders them by `ModuleMeta.depends_on` using a stable tiebreaker (name).

Failures:

- **Import error** (e.g. syntax error in `module.py`) — lenient mode: logged + skipped. Strict mode: raises `InvalidModuleError`.
- **Missing `meta`** — emits `SM001`. Strict mode: raises.
- **Duplicate `meta.name`** — emits `SM008` (error). Always fails boot, even in dev, because names are used as table-name prefixes.
- **Cycle in `depends_on`** — raises `CircularDependencyError`. Always fails boot.

## ModuleMeta

```python
from simple_module_core.module import ModuleMeta

meta = ModuleMeta(
    name="Orders",                    # PascalCase, globally unique
    route_prefix="/api/orders",       # where the API router mounts
    view_prefix="/orders",            # where the view router mounts
    depends_on=["Products"],          # hard ordering requirements
    version="1.0.0",                  # semver for the module
)
```

### `name`

The authoritative identifier. It's used for:

- Table-name prefix (`orders_*`) — every module's tables share the host's single schema on both Postgres and SQLite, so the prefix is what keeps them collision-free.
- Inertia page namespace (`"Orders/Browse"`).
- Diagnostic reporter name.
- Feature-flag and permission grouping.

Rule of thumb: use `PascalCase` and keep it stable. Renaming a module after release requires a data migration and a coordinated client-side rename.

### `depends_on`

A list of other modules' `meta.name` values that **must be loaded first**. The framework topo-sorts on this before invoking lifecycle hooks. Use this when:

- Your module's middleware must sit inside/outside another module's middleware. See [Middleware pipeline](/framework/middleware).
- Your module's `register_routes` reads another module's service to compose endpoints.
- Your module subscribes to events published by another module.

`depends_on` is **not** a dependency-injection mechanism. It only controls order — you still `import` the services you need.

### `version`

Semver string. Used in diagnostic/boot logging to help operators correlate deployed module versions with bug reports. Unless a module declares `requires_framework`, it is not parsed for automated version-range checks.

## The `simple_module` group

Entry points are the same mechanism that ships with `importlib.metadata`:

```text
.venv/lib/python3.12/site-packages/orders-1.0.0.dist-info/entry_points.txt:

    [simple_module]
    orders = orders.module:OrdersModule
```

You can inspect what the framework sees with:

```bash
uv run python -c "
from importlib.metadata import entry_points
for ep in entry_points(group='simple_module'):
    print(ep.name, '->', ep.value)
"
```

## Disabling modules at runtime

Set `SM_MODULES_ENABLED` to a comma-separated allow-list of module names (matched case-insensitively against `ModuleMeta.name`). Useful for:

- Running tests against a minimal world (`SM_MODULES_ENABLED=Users,Orders`).
- Temporarily disabling a misbehaving module in production without a redeploy.
- Sharding a large app into multiple deployments (e.g. background-worker process loads only the `background_tasks` module).

Disabling via env doesn't remove the module's database tables. Re-enabling picks up where it left off.

## Strict-mode checklist

Before flipping to `SM_ENVIRONMENT=production`, verify:

- [ ] Every module's `pyproject.toml` declares the `simple_module` entry point.
- [ ] Every `ModuleBase` subclass has `meta = ModuleMeta(...)`.
- [ ] App boot in development reports no diagnostic errors (`SM001`, `SM008`, `SM009`, `SM010`, `SM016` are all ERROR-level — production boot will fail on any of them).
- [ ] `alembic upgrade head` has been run against the production DB.
- [ ] `SM_SECRET_KEY` is not `change-me-in-production`.

Failure on any of the above produces a clean boot-time exception rather than a silent misbehavior.

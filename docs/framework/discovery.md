# Discovery & entry points

Modules are **Python packages** registered via the `simple_module` entry-point group. There is no module registry file, no `INSTALLED_MODULES` list in settings — if the package is installed in the environment and declares the entry point, it's a module.

## Declaring a module

Every module's `pyproject.toml` ends with:

```toml
[project.entry-points.simple_module]
orders = "orders.module:OrdersModule"
```

- The **key** (`orders`) is the entry-point name. It can select the module before import; the framework's authoritative name remains `ModuleMeta.name`.
- The **value** is `<import_path>:<class_name>`. The class must inherit from `simple_module_core.module.ModuleBase` and declare a non-null `meta = ModuleMeta(...)` class attribute.

Entry points are registered **at install time**, not at import time. After editing a module's `pyproject.toml`, re-run `uv sync --all-packages` (or `make install`) so the installer writes the new metadata to the venv's `*.dist-info/entry_points.txt`.

## Discovery algorithm

`simple_module_core.discovery.discover_modules()`:

1. Iterates `importlib.metadata.entry_points(group="simple_module")`.
2. If every allowlist item matches an installed entry-point name (case-insensitive), excludes unselected entry points **before** calling `.load()` or constructing anything. An empty list imports nothing. Otherwise loads candidates so arbitrary legacy meta names can still match (see [Disabling modules](#disabling-modules-at-runtime)).
3. For each remaining entry point, calls `.load()` to import the module's `module.py` and pull out the class, then instantiates it (`module_cls()`).
4. Validates: the loaded object must be a `ModuleBase` subclass with a `meta` attribute of type `ModuleMeta`.
5. Keeps candidates whose entry-point name **or** `ModuleMeta.name` matches the allowlist, case-insensitively. Reports unknown allowlist entries.
6. Rejects duplicate `meta.name` values among selected modules in strict mode, naming both entry points and their distributions. Development logs `SM008` and skips later entries, retaining the first discovered module. Disabled duplicates do not conflict.
7. Returns a `list` of `ModuleBase` **instances** (one per module, constructed with no args). A separate `topological_sort()` call (made by `create_app`) then orders them by `ModuleMeta.depends_on` using a stable tiebreaker (name). Sorting a manually supplied list also rejects duplicates in strict mode, or warns and keeps the first in lenient mode.

Failures:

- **Import error** (e.g. syntax error in `module.py`) — lenient mode: logged + skipped. Strict mode: raises `InvalidModuleError`.
- **Missing `meta`** — emits `SM001`. Strict mode: raises.
- **Duplicate `meta.name`** — strict discovery raises `InvalidModuleError` (`SM008`), with both distributions. Development logs a warning and skips the later entry. The static diagnostics also report `SM008` errors for duplicate names or table prefixes in a supplied module list.
- **Cycle in `depends_on`** — raises `CircularDependencyError`. Always fails boot.
- **Missing `depends_on` target** (a module that is not installed, not enabled, or dropped because another auth provider was selected) — outside development, `topological_sort(strict=True)` raises one `MissingDependencyError` (an `InvalidModuleError`) naming every `(module, dependency)` pair, and the boot fails. In development it is logged per pair and reported as `SM030` (a warning at boot, an error in `make doctor`). The outbox worker sorts leniently. GH #501.

## ModuleMeta

```python
from simple_module_core.module import ModuleMeta

meta = ModuleMeta(
    name="Orders",  # PascalCase, globally unique
    route_prefix="/api/orders",  # where the API router mounts
    view_prefix="/orders",  # where the view router mounts
    depends_on=["Products"],  # required, and sorted after
    optional_depends_on=["Settings"],  # sorted after when loaded; may be absent
    version="1.0.0",  # semver for the module
    i18n_audience="public",  # who gets this module's locale catalog
    provides_auth=False,  # True if this module installs an AuthProvider
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

`depends_on` is **not** a dependency-injection mechanism. It controls order and presence — you still `import` the services you need. Outside development a missing entry refuses the boot (see Failures above), so list only modules yours cannot work without.

### `optional_depends_on`

Modules to sort after **when they are loaded**, for an ordering-only relationship: your middleware wraps outside theirs, or you subscribe to an event they publish, but your module works without them. Present modules order exactly as `depends_on` would, so moving an entry here never changes the boot order; an absent one is fine in every environment. The modules that sorted after `Settings` only for ordering (`users`, `tenants`, `file_storage`, `background_tasks`, `site_lock`, `api_tokens`, `keycloak`) declare it here, because the settings mechanism lives in the framework (#500) and the `settings` plugin may be disabled.

### `version`

Semver string. When omitted, discovery takes the version from the distribution
owning the entry point, including editable installs. The instance receives new
frozen metadata; the class keeps its `"1.0.0"` default for use outside discovery.
An explicit version wins. Used in diagnostic/boot logging to help operators
correlate deployed module versions with bug reports. Unless a module declares
`requires_framework`, it is not parsed for automated version-range checks.

### `requires_framework`

Optional PEP 440 specifier (e.g. `">=1.0,<2.0"`) for the framework API version the module supports. When set, the module is rejected at boot if the installed `simple_module_core.FRAMEWORK_API_VERSION` doesn't satisfy it. When `None` (the default), no compatibility check runs. See [module authoring](/module-authoring).

### `provides_auth`

Set `provides_auth=True` on a module that installs an `AuthProvider` on
`app.state.auth.auth_provider`. `select_auth_provider()` and the `SM020`/`SM021`
diagnostics use this declaration. Users, Keycloak and OIDC declare it. When
several providers are installed, `SM_AUTH_PROVIDER` selects the one to activate
(default `users`); with only one installed it is kept regardless of that setting.
Outside development, a selection matching none of several providers refuses boot.

The old module class marker `_is_auth_provider = True` remains a fallback until
**0.1.0**, with a `DeprecationWarning` once per legacy module class per process.
Replace it with the metadata field. Provider implementation objects do not need
the marker; the declaration belongs on their owning module.

Static diagnostics warn with `SM020` if the module object itself exposes the
`AuthProvider` shape (`name`, `resolve_user`, `get_login_url`, `get_logout_url`,
`is_bearer_request`) but declares neither the field nor the legacy marker. This
is a structural hint, not signature validation or automatic selection. A separate
provider object created inside a lifecycle hook cannot be detected this way;
its module must declare the field explicitly.

### `i18n_audience`

Who the module's locale catalog is shipped to — `"public"` (the default) or `"admin"`.

Catalogs ride the Inertia shared props on full page loads, so a module whose UI sits entirely behind login can declare `i18n_audience="admin"` and stop anonymous visitors downloading admin form labels on every public page. The catalog is shipped as soon as the user authenticates, and server-side `Translator` lookups always see every namespace either way. See [Internationalization → Audience](/framework/i18n#audience).

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

Set `SM_MODULES_ENABLED` to a JSON list (for example
`SM_MODULES_ENABLED='["Auth","Users","BackgroundTasks"]'`). Items match
entry-point names or `ModuleMeta.name`, case-insensitively. Useful for:

- Running tests against a minimal world (`SM_MODULES_ENABLED='["Auth","Users"]'`).
- Temporarily disabling a misbehaving module in production without a redeploy.
- Sharding a large app into multiple deployments (e.g. background-worker process loads only the `background_tasks` module).

Disabling via env doesn't remove the module's database tables. Re-enabling picks up where it left off.

Bundled entry points use package names (`background_tasks`, `file_storage`),
while metadata uses PascalCase (`BackgroundTasks`, `FileStorage`). Existing
meta-name lists, including CI's e2e/perf lists, continue to work. Discovery does
**not** guess a PascalCase-to-package mapping: third-party names can be unrelated.

To isolate a broken plugin before import, write **every** item using an installed
entry-point name, for example
`SM_MODULES_ENABLED='["auth","users","background_tasks"]'`. In this form only
the named entry points load, even if their metadata names differ. If **any** item
does not match an installed entry-point name (including a typo, a missing package,
or a meta name such as `BackgroundTasks`), discovery must import candidates to
resolve it and then filter by either name. An excluded broken plugin can still
fail strict discovery in that fallback mode. If a token is both an entry-point
name and another plugin's metadata name, the pre-load rule takes precedence when
all tokens resolve to entry points; use the desired plugin's entry-point name to
disambiguate.

## Strict-mode checklist

Before flipping to `SM_ENVIRONMENT=production`, verify:

- [ ] Every module's `pyproject.toml` declares the `simple_module` entry point.
- [ ] Every `ModuleBase` subclass has `meta = ModuleMeta(...)`.
- [ ] Development boot and `make doctor` report no diagnostic errors. Strict production discovery rejects invalid modules, duplicate names and missing dependencies; the static page/locale/coupling suite runs only in development and doctor.
- [ ] `alembic upgrade head` has been run against the production DB.
- [ ] `SM_SECRET_KEY` is not `change-me-in-production`.

Failure on any of the above produces a clean boot-time exception rather than a silent misbehavior.

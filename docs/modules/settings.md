# settings

A DB-backed key/value store with system / tenant / user precedence, plus a per-module pydantic-settings registration system that lets every module's settings be edited from the admin UI and hot-reloaded at runtime.

Two distinct surfaces:

1. **Generic key/value settings** — anything addressable by a string `key`. Useful for arbitrary config you don't want to wedge into a pydantic class. Edited at `/admin/settings/store`.
2. **Per-module pydantic settings** — each module registers a `BaseSettings` subclass via `register_module_settings`. Hydrated from the DB at boot, edited at `/admin/settings/`, hot-swapped on save with a `SettingsReloaded` event so dependents (SMTP clients, Celery configs, …) can rebuild.

Generic store mutations reject keys prefixed by a registered module package with
HTTP 422 and a link to `/admin/settings/` (or its dedicated management
page). Use the module editor/API for validation, environment pinning and reload;
Browse autocomplete offers only declared generic keys (#690).

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Settings` |
| `route_prefix` | `/api/settings` |
| `view_prefix` | `/admin/settings` |
| `depends_on` | _(none)_ |

## Public API for module authors

### Register module settings

The pattern (a `DbBackedSettings` subclass + `register_module_settings` from `simple_module_core.settings.module_settings` in `register_settings`) is documented in [Settings & app.state](/framework/settings#module-settings). Registration and boot-time DB hydration belong to the framework since #500 and work with this module disabled. What the settings module adds on top:
- **Env-var migration**: `smpy settings import-from-env` imports legacy `SM_*` variables for registered DB settings fields as SYSTEM-scoped rows, with optional module/prefix filters and validation. See [CLI](#cli).
- **Admin editing**: registered fields appear under that package at `/admin/settings/` with type-aware inputs.
- **Hot reload**: saving via the admin UI calls `apply_changes_and_reload`, which validates the diff against the pydantic class, persists deltas, swaps the live `app.state.<package>.settings`, and publishes [`SettingsReloaded`](#events) so dependents (SMTP clients, Celery configs, …) can rebuild.

### Read DB-backed settings outside the web process

`DbBackedSettings` subclasses ignore the environment, and only the hosting lifespan hydrates `app.state.<package>.settings`. A Celery worker (or CLI script) never runs that lifespan, so a bare `FileStorageSettings()` there silently returns pydantic defaults. Hydrate synchronously instead:

```python
from simple_module_db.stored_settings import hydrate_settings_sync

cfg = hydrate_settings_sync(FileStorageSettings, session, "file_storage")
```

`session` is a plain sync SQLAlchemy `Session`. Precedence matches the web process (SYSTEM-scope DB overrides over pydantic defaults, same `value_type` parsing, no env). Inside a Celery task prefer `background_tasks.settings_for(FileStorageSettings, "file_storage")`, which opens the worker's sync session and caches the result per process for 30 seconds (`ttl=` to change, `0` to always re-read).

### Read settings at request time (generic K/V)

```python
from settings.contracts import SettingsDep


@router.get("/check")
async def check(settings: SettingsDep) -> dict:
    if await settings.get_bool("checkout.beta", default=False):
        ...
    timeout_ms = await settings.get_int("checkout.timeout_ms", default=5000)
```

`SettingsDep` resolves a request-scoped `SettingsAccessor` bound to the current `user_id` + `tenant_id`. Lookups follow **USER → TENANT → SYSTEM → default** precedence.

| Method | Returns |
|---|---|
| `get(key, default=None)` | raw stored value |
| `get_str` / `get_bool` / `get_int` / `get_float` / `get_json` | typed helpers |
| `get_typed(key, default=None)` | resolves and casts using the row's stored `value_type` |
| `bind(user_id=..., tenant_id=...)` | a new accessor with overrides — useful for background jobs |
| `set_system(key, value, value_type=None, description=None)` | upsert at SYSTEM scope |
| `set_tenant(tenant_id, key, value, ...)` | upsert at TENANT scope |
| `set_user(user_id, key, value, ...)` | upsert at USER scope |

### Register a setting definition (so admins can see defaults)

Define module-owned settings as typed fields. The field default and description
appear in the module editor at `/admin/settings/`.

```python
from dataclasses import dataclass

from fastapi import FastAPI
from pydantic import Field
from simple_module_core.modules.module import ModuleBase, ModuleMeta
from simple_module_core.settings.module_settings import register_module_settings
from simple_module_core.settings.settings_base import DbBackedSettings


class OrdersSettings(DbBackedSettings):
    beta: bool = Field(default=False, description="Enable the new checkout flow.")


@dataclass
class OrdersServices:
    settings: OrdersSettings


class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="Orders")

    def register_settings(self, app: FastAPI) -> None:
        register_module_settings(app, "orders", OrdersSettings, OrdersServices)
```

Read the hydrated setting as `request.app.state.orders.settings.beta`. Register
scoped generic K/V keys separately with `app.state.settings.registry.add`
and a `SettingDefinition`, as in the next example. Modules using that
registry must declare a dependency on `Settings`.

### Tenant-overridable keys

A definition with `tenant_overridable=True` can be changed by a tenant for
itself (#382). Tenant owners and admins hold `settings.tenant.edit` (mapped onto
`tenant:owner` / `tenant:admin`; members get nothing) and write through
`/api/settings/tenant/current/{key}`, which acts on `request.state.tenant_id`
only — the tenant never comes from the URL. Keys without the flag answer 422
there; a request acting for no tenant gets 403. The `tenants` module renders
these keys at `/tenants/settings`.

```python
from settings.contracts import SettingDefinition


async def check_logo(request, tenant_id: str, value: str) -> None:
    if value and not await tenant_owns_file(request.app, tenant_id, value):
        raise LookupError("unknown file")  # -> 404; ValueError -> 422


# In the consuming module's register_settings hook:
app.state.settings.registry.add(
    SettingDefinition(
        key="tenant_branding.logo",
        tenant_overridable=True,
        check=check_logo,
    )
)
```

`check` runs before **every** TENANT-scope write of the key — the self-service
route and the platform routes alike, with the tenant being written (not the
caller's). The declared `value_type` wins over the one a tenant sends. `upload_url` marks a file-id key (a logo): the tenant settings page offers an upload to that URL (POST, DELETE to clear) instead of a text box.

Runtime reads need nothing new: `SettingsDep` is already bound to the active
tenant, so `await settings.get(key)` resolves **tenant → system → default**.

### Cache invalidation

Every SYSTEM / TENANT write publishes on the `settings.values`
[invalidation](/framework/invalidation) channel after commit, keyed per
(tenant, key): `"<tenant_id>|<key>"`, or `"|<key>"` for a system write (every
tenant inheriting it is affected). `settings.contracts.invalidation` builds and
parses the key. Settings caches nothing itself; a module that caches a resolved
per-tenant value subscribes and forgets.

## Routes

### Generic K/V API (`/api/settings/...`)

All write endpoints require `settings.edit` / `settings.create` / `settings.delete`; reads need `settings.view`. These are platform-operator permissions: no tenant role holds them, and the holder may write generic keys at system scope or at any tenant's scope; registered module namespaces must use the module editor/API. A TENANT `scope_id` must name a real tenant when a tenant-owning module is installed (`simple_module_core.access.tenancy.tenant_exists`): 404 on the `/tenant/{scope_id}/…` GET/PUT, 422 for a `POST /` body. `DELETE` stays unvalidated so a deleted tenant's leftovers can be cleared. A key declaring `SettingDefinition.clear_via` (a file set through an upload route, which reaps the stored file) is protected inside `SettingService.delete` / `delete_scoped`, so it holds for every scope (SYSTEM, TENANT, USER) and every caller: a generic delete raises `ManagedKeyError`, which the API maps to 422 naming that route (`clear_via` may be a `{SettingScope: route}` mapping when system and tenant rows clear differently; the 422 names the route for the row's scope, via `clear_route`) and the Inertia store screen shows as a toast. Two deliberate ways through: the owner of the key passes `as_owner=True` after taking responsibility for the file (branding's tenant clear route reaps it), and a TENANT row whose tenant no longer exists may be cleared by a platform operator. The guard needs the registry, which `get_setting_service` supplies; a bare `SettingService(db)` guards nothing.

| Method + path | Purpose |
|---|---|
| `GET /api/settings/` | list all (`?scope=&scope_id=`) |
| `GET /api/settings/resolve/{key}` | precedence resolution (`?user_id=&tenant_id=`) |
| `GET / PUT / DELETE /api/settings/system/{key}` | system-scope CRUD |
| `GET / PUT / DELETE /api/settings/tenant/{scope_id}/{key}` | tenant-scope CRUD |
| `GET / PUT / DELETE /api/settings/user/{scope_id}/{key}` | user-scope CRUD |
| `GET /api/settings/tenant/current` | the active tenant's overridable keys: `inherited`, own `value`, `effective` (`settings.tenant.edit`) |
| `GET / PUT / DELETE /api/settings/tenant/current/{key}` | the active tenant's override of an overridable key (`settings.tenant.edit`) |
| `POST /api/settings/` | create with explicit `scope` + `scope_id` (`SettingCreate`) |
| `GET / PUT / DELETE /api/settings/{setting_id}` | by-id CRUD |

### Module settings API

| Method + path | Purpose |
|---|---|
| `GET /api/settings/modules` | autodiscovered per-module settings + current values |
| `PUT /api/settings/modules/{package}` | apply field changes; hot-reload |
| `DELETE /api/settings/modules/{package}/{field}` | revert one field to its pydantic default |

### View

| Method + path | Inertia component |
|---|---|
| `GET /admin/settings/` | `Settings/Browse` |
| `GET /admin/settings/create` | `Settings/Create` |
| `GET /admin/settings/{setting_id}/edit` | `Settings/Edit` |
| `GET /admin/settings/modules` | legacy redirect → `/admin/settings/` |
| `POST` / `PUT` / `DELETE /admin/settings/...` | form actions; redirect to `/admin/settings` |

## Public contracts

```python
from settings.contracts import (
    SettingOut,
    SettingCreate,
    SettingUpdate,
    SettingUpsert,
    SettingScope,
    SettingValueType,
    SettingsAccessor,
    SettingsDep,
    SettingsRegistry,
    SettingDefinition,
    SettingsReloaded,
)
```

| Class | Purpose |
|---|---|
| `SettingOut` | Persisted row: `id`, `scope`, `scope_id`, `key`, `value`, `value_type`, `description`, `created_at`, `updated_at`. |
| `SettingScope` (enum) | `SYSTEM` / `TENANT` / `USER`. |
| `SettingValueType` (enum) | `STRING` / `BOOL` / `INT` / `FLOAT` / `JSON`. |
| `SettingsAccessor` | Request-scoped facade (described above). |
| `SettingsRegistry` | In-memory definition registry. |
| `SettingsReloaded` (event) | Published after `apply_changes_and_reload`. Fields: `package: str`, `changed: tuple[str, ...]`. |

## Models

`Setting` (table `settings_setting`)

| Column | Type | Notes |
|---|---|---|
| `id` | `int` | PK |
| `scope` | `str` | `system` \| `tenant` \| `user`; indexed |
| `scope_id` | `str` | empty string for system scope; indexed |
| `key` | `str` | indexed |
| `value` | `str` | string-encoded; cast via `value_type` |
| `value_type` | `str` | `string` (default), `bool`, `int`, `float`, `json` |
| `description` | `str \| None` | |
| audit | from `AuditMixin` | |

Unique constraint on `(scope, scope_id, key)`.

## Lifecycle (boot + reload)

1. **`register_settings`** (each module) calls `register_module_settings(app, package, cls, services_factory)`. The framework records the class in the app's registry and calls the factory to populate `app.state.<package>`.
2. **Boot hydration** replaces each `app.state.<package>.settings` with a fresh instance built from stored overrides and defaults before the module startup hooks run.
3. **At runtime** — admin saves via `PUT /api/settings/modules/{package}`. `apply_changes_and_reload(app, bus, store, package, changes)` validates the diff against the pydantic class, persists deltas, hot-swaps `app.state.<package>.settings`, publishes `SettingsReloaded(package, changed=(...))`.
4. **Subscribers** — modules listen for `SettingsReloaded` and rebuild stateful handles (e.g. the SMTP client) when their package matches.

## Permissions

| Code | Purpose |
|---|---|
| `settings.view` | read settings |
| `settings.create` | create new K/V rows |
| `settings.edit` | update existing rows / module fields |
| `settings.delete` | delete rows / clear module fields |

## Menu

| Label | URL | Icon | Section | Group | Order |
|---|---|---|---|---|---|
| `Settings` | `/admin/settings/` | `settings` | `ADMIN_SIDEBAR` | `System` | `200` |

## Events

- `SettingsReloaded(package, changed)` — published after a successful module-settings save.

## CLI

`smpy settings import-from-env` migrates legacy `SM_<PREFIX>_<FIELD>` variables
to SYSTEM-scope DB overrides. The project `.env` is read first, then process
variables take precedence. Repeating the command upserts the selected overrides,
including existing rows. Restart application processes to load the changes.

Production images do not need `simple_module_cli`: use the settings package's
own entry point with the same arguments:

```bash
python -m settings import-from-env --only file_storage
smpy settings import-from-env --only file_storage --only mail
python -m settings import-from-env --prefix SM_FILE_STORAGE_ --prefix SM_MAIL_
```

`--only` accepts settings package names case-insensitively (`file_storage`,
not the display name `FileStorage`). Unknown names fail and list the registered
packages. `--prefix` matches variable names by prefix (normalized to uppercase).
Both options are repeatable; their matches are combined, so a variable selected
by either is eligible. Without filters, all matching registered fields are
eligible. Prefixes use the historical importer mapping: usually
`SM_<PACKAGE>_`, with `SM_BG_TASKS_` for `background_tasks` and `SM_` for `host`.

Values are parsed as their stored type, checked against the store's write schema,
then checked by the settings class's field constraints and validators, including
model validators across selected values, existing DB overrides and class defaults.
Validation bypasses Pydantic's environment/dotenv sources. Defaults and validators
that read the process environment directly still run, including the
`background_tasks` defaults seeded by `SM_REDIS_URL`.
Any invalid value aborts the entire import
before writing, prints variable names and validation error types, and exits
non-zero. Successful output lists each stored `<package>.<field>` without its
value and ends with the imported count. Failed validation reports a count of zero.
Validator messages are omitted because they can contain submitted values.

There is no general env-only field marker in `DbBackedSettings` or the settings
registry; secret-redaction metadata does not mean a field is env-only. The
importer only accepts fields in registered DB settings classes. Other selected
`SM_*` variables are reported as skipped (env-only or unknown), including host
bootstrap/process wiring and Users bootstrap passwords and legacy token secrets,
which are not registered DB fields. It never creates arbitrary rows for them.
Some `SM_BG_TASKS_*` fields and registered Keycloak fields **are** DB-hydrated
in this framework and remain eligible; the importer does not block entire
prefixes. Host and env-readable background-task fields still follow
env → DB → default precedence: remove their legacy env variables after migration
if future DB edits should take effect. Keycloak reads its bootstrap environment
values into class defaults at import time; stored DB overrides take precedence
over those defaults.

## Inertia pages

- `Settings/Browse.tsx` — generic K/V browse + filter.
- `Settings/Create.tsx`, `Settings/Edit.tsx` — generic K/V CRUD forms.
- `Settings/ModulesEdit.tsx` — per-module settings panel; one section per registered module.

## Locales

Top-level keys in `settings/locales/en.json`: `browse`, `table`, `scopes`, `value_types`, `form`, `create`, `edit`, `modules`.

## Notes

- The K/V store treats `value` as a string and casts on read using `value_type` — that's deliberate: it lets you store anything (including JSON blobs) without a per-type column.
- The `services_factory` receives the initial settings instance and returns a container with a writable `.settings` attribute for hydration and reload.

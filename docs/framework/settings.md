# Settings & app.state

There are **three** separate settings surfaces in a running app. They serve different purposes and live in different places.

| Surface | Lives in | Mutable at runtime? | Use for |
|---|---|---|---|
| **Framework env** (`Settings`) | `app.state.sm.settings` | No (read once at boot) | DB URL, secret key, log level, anything needed before the DB is open. |
| **Module env** (`<Module>Env`) | `app.state.<module>.settings` | No | Module bootstrap knobs that must be resolved before DB-backed settings load. |
| **DB-backed settings** | `settings_setting` table, edited via `/admin/settings/` | Yes | Everything else: SMTP creds, storage backends, feature toggles that operators tune. |

## Framework settings

`Settings` (in `simple_module_hosting.config.settings`) combines `BootstrapSettings` (env-only, read before the DB is open) and `HostSettings`. The pre-DB knobs are a pydantic `BaseSettings` subclass:

```python
class BootstrapSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./app.db"
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    vite_dev_url: str = "http://localhost:5050"
    debug: bool = False
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    modules_enabled: list[str] | None = None
    auth_public_paths: list[str] = []
```

The `SM_` prefix means every field is set via `SM_<FIELD>` (e.g. `SM_DATABASE_URL`, `SM_LOG_FORMAT`). `multi_tenant` / `tenant_header` and the other tunables live on the DB-backed `HostSettings` half.

The public `build_host_app()` factory calls `merge_host_settings()` before
`create_app` to apply stored host
settings before middleware and module discovery are built. Precedence is
**env → DB → default**. Here, env includes the discovered project `.env`;
process environment variables take precedence over that file. Both the boot
`Settings` and runtime `HostSettings` discover the same file via
`find_env_file()`, including from a project subdirectory, without requiring
`load_dotenv_into_environ()` first. Direct settings construction supports an
explicit `_env_file` path or `_env_file=None` to disable dotenv loading.

A host entry point can delegate the complete boot sequence:

```python
from simple_module_hosting.boot.host import build_host_app

app = build_host_app(__file__, routers=("routes:router",))
```

The factory pins the entry directory on `sys.path`, publishes `SM_PROJECT_ROOT`,
changes to the project root and loads dotenv into `os.environ` **before importing
settings or application code**. This order also covers code reading environment
variables directly. Router import strings defer their imports until after dotenv;
pre-built `APIRouter` instances are supported when no deferred import is needed.
The existing package exports remain available, loaded lazily to preserve this order.

Project-root discovery starts at the entry directory and uses the same markers
as the CLI and migration checks. Pass `project_root=` for a custom layout. An existing
`SM_PROJECT_ROOT` wins over either. This is process startup code: configure one host
per process. Keep app-specific additions after the call and read boot settings from
`app.state.sm.settings`. `create_app` retains its development-only extras.
Restart-required fields are still merged before middleware and module discovery;
calling `Settings()` instead would bypass DB overrides at that stage.

The set of env-supplied fields is cached once per settings class per process,
including custom sources and `env_seeded_fields`. Configure process variables,
`.env`, and secret files before the first settings hydration; changing these
sources at runtime requires a process restart. DB-backed settings remain
live-editable. The default API version (installed host version or project
`pyproject.toml` fallback) is also discovered once per process.

When passing a `BootstrapSettings` to `merge_host_settings(bootstrap)`, every
field explicitly supplied on that object is preserved, including `environment`,
`modules_enabled`, `redis_url`, `debug` and `vite_dev_url`. The resolved secret
key and database URL are preserved too. Fields the bootstrap did not supply
still use env → DB → default.

Construct once at boot, put on `app.state.sm.settings`, never mutated.
Runtime readers use `app.state.host.settings`, replaced after a committed admin
save and by the existing cross-process settings invalidation/reload.

### Shared host policy

Set `host.public_base_url` once for canonical URLs, account emails, copied
account links and tenant invitations. Blank `users.base_url` and
`tenants.public_base_url` inherit it. Explicit module origins win.
The shared `simple_module_hosting.pipeline.public_urls.public_origin` helper
uses configured origins, with relative URLs as the default for copied
account and tenant invitation links.

When both account email origins are blank, `trusted_request_origin(request)`
can supply an origin for password reset, verification and invitation emails.
It uses the scheme and authority resolved by the hosting middleware.
`host.forwarded_host_allowlist` must match the authority using the same exact
host, wildcard subdomain and optional port rules as [ForwardedHost](/framework/middleware#forwardedhostmiddleware-opt-in).
The middleware accepts `X-Forwarded-Host` only from a trusted proxy. HTTPS is
eligible for any allowlisted host. HTTP requires a trusted proxy peer or a
loopback host (`localhost`, its subdomains, `127.0.0.0/8` or `[::1]`), which must also be
allowlisted. Use brackets when listing an IPv6 address and add an optional
port after the closing bracket.

If there is no eligible request origin, including sends without a request,
the mailer skips delivery and logs an ERROR naming `host.public_base_url`.
Public reset and verification responses stay generic.
An explicitly stored users origin, including the old localhost default, keeps
winning. Clear it to inherit the host.

`host.session_cookie_secure` controls both session and users auth cookies.
Unset means Secure outside development/testing and HTTP-compatible within them;
changing it needs a restart. `host.login_redirect_url` is the live post-login
destination for Users, Keycloak and OIDC. It defaults to `/dashboard/`; without
Dashboard each provider chooses the first other module with view routes, then
`/`. Safe saved deep links still take precedence.

The old provider `login_redirect_url` and `users.cookie_secure` fields are no
longer read; move any overrides to the corresponding host field. The unused
`keycloak.admin_role` and `background_tasks.max_retries` fields are also removed;
use Keycloak role mapping and each task's retry policy. User provisioning reads
only the documented `SM_USERS_BOOTSTRAP_*` environment/dotenv keys, never DB
bootstrap fields. Unknown stored module keys are ignored quietly, including all
these removed fields; no schema migration or cleanup is needed.

### Live request guards

`max_request_body_bytes`, `rate_limit_public`, `rate_limit_authenticated` and
all six `cors_*` host fields apply after a committed settings reload, without a
restart. Hydration validates and compiles one immutable policy snapshot; every
request retains one snapshot across its guards, with no per-request DB lookup
or rate parsing. Runtime guard values follow hydration, so configure them in
the DB or process environment rather than only passing an unpersisted boot
`Settings` object to `create_app`. Module-registered body, rate and CORS rules keep their existing
precedence. Invalid admin writes are rejected before persistence; invalid old
rows follow the existing lenient parsing rules. Env-pinned values still win.


### Root signing key

`SM_SECRET_KEY` is optional. `merge_host_settings()` resolves an explicit value,
then a stored key, then generates and stores one. An explicit value is never
copied into the DB. Outside development, pre-app read or persistence failures
refuse boot; only a confirmed missing settings table permits an ephemeral key.
After migrations, setup persists a generated root and adopts the stored winning
value before replaying module startup. Other first-run workers adopt that same
value when they observe the completed migrations. Persistence failures keep the
setup gate closed. Production still refuses the shipped root placeholder.

The resolved root is available at `app.state.boot_settings.secret_key` before
module settings registration, and at `app.state.sm.settings.secret_key` once
the complete services container is built. Users derives password-reset and email-verification
keys with HKDF-SHA256 using `simple-module/v1/users/password-reset` and
`simple-module/v1/users/email-verification`. Users resolves keys lazily from the
current root, caching them per root value, so links issued after setup survive
restarts. Editable DB module settings hydration and reloads cannot change them.
Explicit non-placeholder
legacy users token-secret env overrides log a deprecation warning and remain
supported until 0.0.50. Existing links signed by other keys need to be reissued.
Identity-provider, SMTP, S3 and Sentry credentials remain separate external credentials.

## Module settings

Each module that needs configuration declares a `DbBackedSettings` subclass
(constructor + DB, no env source) and a services dataclass that bundles the
settings with any runtime singletons, then registers both from
`register_settings`:

```python
# modules/orders/orders/settings.py
from pydantic_settings import SettingsConfigDict
from simple_module_core.settings.settings_base import DbBackedSettings


class OrdersSettings(DbBackedSettings):
    model_config = SettingsConfigDict(extra="ignore")

    max_items_per_order: int = 100
```

```python
# modules/orders/orders/module.py
from simple_module_core.settings.module_settings import register_module_settings


class OrdersModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        from orders.services import OrdersServices
        from orders.settings import OrdersSettings

        register_module_settings(
            app, "orders", OrdersSettings, lambda s: OrdersServices(settings=s)
        )
```

`register_module_settings` records the class in the app's
`ModuleSettingsRegistry` and mounts `services_factory(OrdersSettings())` on
`app.state.orders`. The hosting lifespan then replaces
`app.state.orders.settings` with an instance hydrated from the
`settings_setting` table (env → DB → default) before any `on_startup` runs.

The whole mechanism lives in the framework (#500), so it works whether or not
the `settings` plugin is enabled; the plugin adds the admin editor, hot
reload and the generic key/value API on top.

| What | Import from |
|---|---|
| `register_module_settings`, `ModuleSettingsRegistry`, `module_settings_registry(app)` | `simple_module_core.settings.module_settings` |
| `hydrate_settings`, `build_settings`, `OverrideSource`, `RELATED_FIELDS_CTX`, field helpers | `simple_module_core.settings.settings_hydrate` |
| Secret-field masking (`conceals_secret`, `mask`, ...) | `simple_module_core.settings.secret_fields` |
| `Setting` model, scope/table constants, `get_overrides_sync`, `hydrate_settings_sync` | `simple_module_db.queries.stored_settings` |

Import directly from the framework locations above. The settings plugin keeps
its `settings.models` model identity and its area-level store, constants and
secret helpers; the deprecated root import paths were removed in #989.

A Celery worker or CLI script never runs the lifespan, so it hydrates
synchronously:

```python
from simple_module_db.queries.stored_settings import hydrate_settings_sync

cfg = hydrate_settings_sync(OrdersSettings, session, "orders")
```

### Why `app.state.<module_lower>`?

- **Discoverable.** Every module follows the same pattern; diagnostics check for it (`SM012`).
- **Type-safe.** Code reads `request.app.state.users.settings.allow_signup` with full IDE autocomplete.
- **No global state.** The app instance owns it; tests get a fresh one per fixture.

### Accessing from an endpoint

```python
from fastapi import Request


@router.get("/config")
async def users_config(request: Request):
    state = request.app.state.users
    return {"allow_signup": state.settings.allow_signup}
```

Or as a typed dependency — cleaner when you use it in many handlers:

```python
# modules/users/users/web/deps.py
from typing import Annotated
from fastapi import Depends, Request


def _users_state(request: Request) -> UsersState:
    return request.app.state.users


UsersStateDep = Annotated[UsersState, Depends(_users_state)]


@router.get("/config")
async def users_config(state: UsersStateDep):
    return {"allow_signup": state.settings.allow_signup}
```

## DB-backed settings

After bootstrap, most configuration lives in the `settings_setting` table and is edited via the admin UI at `/admin/settings/`. The CRUD layer is `SettingService` (in `settings.core.service`); typed reads (with USER > TENANT > SYSTEM resolution and registered defaults) go through a `SettingsAccessor` that wraps it:

```python
from settings.core.service import SettingService
from settings.contracts.accessor import SettingsAccessor

accessor = SettingsAccessor(SettingService(session), registry)
max_size = await accessor.get_int("file_storage.max_upload_mb", default=10)
```

Values are keyed by `<namespace>.<key>`. Conventional namespace is the module name lowercased.

### Seeding from env on upgrade

Existing deployments that used env vars for module settings should run once:

```bash
uv run smpy settings import-from-env
```

This reads the current environment, looks up keys the settings service knows about, and writes overrides into the DB. Idempotent — skips keys that already have a DB override. After running, you can remove those env vars from deployment config.

## Framework state (`app.state.sm`)

Framework singletons — not settings, but long-lived services — live on `app.state.sm`, a frozen `Services` dataclass (defined in `simple_module_core.modules.services`) populated once at boot:

```python
@dataclass(frozen=True, slots=True)
class Services:
    settings: Settings
    db: DatabaseState
    event_bus: EventBus
    menu_registry: MenuRegistry
    permissions: PermissionRegistry
    feature_flags: FeatureFlagRegistry
    health_registry: HealthRegistry
    public_routes: PublicRouteRegistry
    i18n_registry: I18nRegistry
    inertia_config: InertiaConfig
    modules: tuple[ModuleBase, ...]
```

**Read** from a request: `request.app.state.sm.<field>`.
**Never** mutate `app.state` for framework-owned state — add a field to `Services` if you need new shared infrastructure.

Two attributes are intentionally outside `Services`:

- `app.state.inertia_dependency` — request-scoped `Depends` factory, provided by the fastapi-inertia package (framework doesn't own the type).
- `app.state.migration` — a dev-only boot-time migration check result set inside the lifespan (after `Services` is already frozen).

## Diagnostic: `SM012`

Fires at dev-boot if a module overrides `register_settings` but does **not** assign anything to `app.state.<module_lower>`. Interpretations:

- The override is vestigial — delete it (revert to `pass` or remove the method).
- You stored state under a non-standard key — rename to `app.state.<module_lower>` so other tooling can find it.
- You're attaching state inside a different hook (e.g. `on_startup`). Move settings creation to `register_settings`; `on_startup` should assume `app.state.<module>` already exists.

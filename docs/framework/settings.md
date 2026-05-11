# Settings & app.state

There are **three** separate settings surfaces in a running app. They serve different purposes and live in different places.

| Surface | Lives in | Mutable at runtime? | Use for |
|---|---|---|---|
| **Framework env** (`Settings`) | `app.state.sm.settings` | No (read once at boot) | DB URL, secret key, log level, anything needed before the DB is open. |
| **Module env** (`<Module>Env`) | `app.state.<module>.settings` | No | Module bootstrap knobs that must be resolved before DB-backed settings load. |
| **DB-backed settings** | `sm_settings.settings` table, edited via `/settings/modules` | Yes | Everything else: SMTP creds, storage backends, feature toggles that operators tune. |

## Framework settings

Defined as a pydantic `BaseSettings` subclass in `simple_module_hosting.settings`:

```python
class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./app.db"
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    vite_dev_url: str = "http://localhost:5050"
    debug: bool = False
    log_level: str = "INFO"
    log_format: str = "plain"
    multi_tenant: bool = False
    tenant_header: str = "X-Tenant-ID"
    modules_enabled: list[str] | None = None

    class Config:
        env_prefix = "SM_"
```

Construct once at boot, put on `app.state.sm.settings`, never mutated.

### Placeholder-secret check

In production (`environment != "development"`), boot fails if `secret_key == "change-me-in-production"`. The check runs before middleware installation to avoid issuing signed cookies against a known-placeholder key.

## Module settings

Each module that needs configuration declares a **`<Module>Env`** pydantic-settings class with its own `env_prefix` and a **`<Module>State`** dataclass to bundle settings plus any runtime-computed singletons.

```python
# modules/users/users/settings.py
from pydantic_settings import BaseSettings

class UsersEnv(BaseSettings):
    allow_signup: bool = False
    mailer: str = "console"
    base_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None

    class Config:
        env_prefix = "SM_USERS_"
```

```python
# modules/users/users/state.py
from dataclasses import dataclass

@dataclass
class UsersState:
    settings: UsersEnv
    mailer: Mailer              # picked based on settings.mailer
    principal_serializer: Callable[[User], dict]
```

Attach in `register_settings`:

```python
# modules/users/users/module.py
class UsersModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        settings = UsersEnv()
        app.state.users = UsersState(
            settings=settings,
            mailer=build_mailer(settings),
            principal_serializer=serialize_user,
        )
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
# modules/users/users/deps.py
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

After bootstrap, most configuration lives in the `sm_settings.settings` table and is edited via the admin UI at `/settings/modules`. Reads go through `SettingsService` which caches in-memory with invalidation on write:

```python
from settings.service import SettingsService

service = SettingsService(session)
max_size = await service.get_int("file_storage.max_upload_mb", default=10)
```

Values are keyed by `<namespace>.<key>`. Conventional namespace is the module name lowercased.

### Seeding from env on upgrade

Existing deployments that used env vars for module settings should run once:

```bash
uv run smpy settings import-from-env
```

This reads the current environment, looks up keys the settings service knows about, and writes overrides into the DB. Idempotent — skips keys that already have a DB override. After running, you can remove those env vars from deployment config.

## Framework state (`app.state.sm`)

Framework singletons — not settings, but long-lived services — live on `app.state.sm`, a frozen `Services` dataclass populated once at boot:

```python
@dataclass(frozen=True)
class Services:
    settings: Settings
    db: DatabaseState
    event_bus: EventBus
    menu_registry: MenuRegistry
    permissions: PermissionRegistry
    feature_flags: FeatureFlagRegistry
    health_registry: HealthRegistry
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

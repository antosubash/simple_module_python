# Framework overview

simple_module_python is a **modular-monolith framework**. The framework is `framework/core`, `framework/db`, and `framework/hosting` — three packages that provide the module system, DB session management, and the FastAPI app builder. Everything else is a plugin module.

```text
framework/
  core/      # ModuleBase, discovery, event bus, diagnostics
  db/        # create_module_base, mixins, session lifecycle
  hosting/   # create_app, middleware pipeline, settings
```

The framework has **no knowledge of any specific plugin module**. Diagnostic `SM009` fires as an error if framework code imports from anything under `modules/*`.

## Boot sequence

What actually happens when you run `uvicorn main:app`:

1. **`build_host_app(__file__, routers=("routes:router",))`** in the host entry point loads dotenv, merges host settings and configures logging, then invokes `create_app(settings)`. FastAPI runs the lifespan when the app starts.
2. **Framework singletons** are constructed:
   `Settings`, `DatabaseState` (engines per provider), `EventBus`, `MenuRegistry`, `PermissionRegistry`, `FeatureFlagRegistry`, `HealthRegistry`, `I18nRegistry`. They are bundled into a frozen `Services` dataclass and attached to `app.state.sm`.
3. **Discovery** — `discover_modules()` reads Python entry points under the `simple_module` group, imports each one, validates it's a `ModuleBase` subclass with a non-null `meta`, and topologically sorts by `ModuleMeta.depends_on`.
4. **Lifecycle hooks run in sorted order**. For each module, in this order:
   `register_settings` → `register_menu_items` → `register_permissions` → `register_feature_flags` → `register_event_handlers` → `register_health_checks` → `register_public_routes` → `register_csp_sources` → `register_design_packs` → `register_exception_handlers` → `register_middleware` → `register_routes(api_router, view_router)`.
5. **Middleware is installed** — framework middleware first, then whatever modules registered. See [Middleware pipeline](/framework/middleware).
6. **Routers mount** — `api_router` at `/api`, `view_router` at `/`. Each module's sub-routers were attached via `register_routes`.
7. **Lifespan `on_startup`** — each module's async `on_startup` runs in dependency order. This is where background workers, warm caches, or remote-service health probes start.
8. **Migration-head check (dev only)** — compares `alembic_version` to the migration head and logs a warning if behind. In production this is a hard failure (`SM010`). Result goes on `app.state.migration`.
9. App is ready to serve.

On shutdown, `on_shutdown` hooks run in **reverse** order.

## Custom database state

Both builders accept `database=state` or
`database=lambda settings: make_database(settings)`. The factory runs once
during app construction with resolved settings and returns a `DatabaseState`,
which becomes `app.state.sm.db`. This supports custom engines, `async_creator`
connections and session routing to read replicas without creating the default
application engine. See [Database engines and ownership](/database/tuning#supplying-an-engine-and-session-factory)
for the session-factory contract.

Injected states and factory results are caller-owned: lifespan shutdown and
startup-failure cleanup leave their engines open. Dispose them in the caller
after the app stops. Without `database`, the framework creates and disposes
the engine as before.

`build_host_app` still merges stored host settings before invoking `create_app`,
and `create_app()` without explicit settings does the same. These preliminary
settings reads and CLI/Alembic operations use the configured database URL;
database injection replaces the application's runtime state. For a connection
available only through a custom creator, pass explicit resolved `Settings` to
`create_app(settings, database=...)` to avoid the preliminary settings read.

## Strict mode vs. lenient mode

Discovery and diagnostics behave differently based on `SM_ENVIRONMENT`:

| Environment | Mode | Behavior |
|---|---|---|
| `development` (default) | Lenient | Entry-point load errors are logged; the module is skipped. `SM001` warnings printed. |
| `test`, `testing` | Lenient | Same as development, so fixtures can load partial worlds. |
| Anything else (e.g. `production`) | Strict | Any missing `meta`, duplicate name (`SM008`), framework→plugin import (`SM009`), or DB drift (`SM010`) fails boot. |

The distinction exists so developer ergonomics aren't gated on fixing every warning, but production deployments can't silently run with broken modules.

## The Services container

Framework singletons live on `app.state.sm`, a frozen dataclass defined in `simple_module_core.modules.services`:

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

Read from a request with `request.app.state.sm.<field>`. **Do not** attach new attributes to `app.state` for framework-owned state — that's what `Services` is for. Two attributes are intentionally kept outside:

- `app.state.inertia_dependency` — request-scoped `Depends` factory from fastapi-inertia.
- `app.state.migration` — the dev-only boot-time migration check result.

Module-owned state goes on `app.state.<module_lower>` (a per-module dataclass you define). See [Settings & app.state](/framework/settings).

## Framework vs. plugin boundary

Framework code must never import from `modules/*`. Diagnostic `SM009` enforces this at CI time. To invert dependencies when framework code needs per-module behavior, register a callback from the module:

```python
# Framework defines a registry
class PrincipalSerializerRegistry:
    def register(self, fn: Callable[[User], dict]) -> None: ...


# Module registers during register_settings
class UsersModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        app.state.sm.inertia_config.register_principal_serializer(serialize_user)
```

This is how the `auth.user` shared prop is built: framework middleware calls whatever serializer the `users` module registered — without importing `users`.

## Next steps

- [Discovery & entry points](/framework/discovery) — how modules are installed and found.
- [Lifecycle hooks](/framework/lifecycle) — the lifecycle hooks in call order with examples.
- [Middleware pipeline](/framework/middleware) — execution order and how to slot your own in.
- [Settings & app.state](/framework/settings) — framework vs. module state.
- [Bundled modules](/modules/) — the twelve first-party modules and what each one ships.

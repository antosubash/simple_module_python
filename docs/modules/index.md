# Bundled modules

simple_module_python ships with eleven first-party modules. Each is a regular Python package — same shape as a module you'd write yourself — registered through the `simple_module` entry point and discovered at boot. They are independent: install only what you need.

| Module | Depends on | What it provides |
|---|---|---|
| [`auth`](/modules/auth) | — | Tiny public surface (`UserContext`, `AuthProvider`, `get_current_user`, `require_permission`) other modules import, plus the provider-agnostic `AuthMiddleware` and principal-resolver chain. The actual login/session logic lives in an auth-provider module (`users` or `keycloak`). |
| [`users`](/modules/users) | `auth` | Email + password auth, OAuth/OIDC (Google, GitHub, Microsoft/Entra ID, generic OIDC), sessions, roles, invites, password reset, email verification, admin UI, mailer backends, `smpy users create-admin`. |
| [`keycloak`](/modules/keycloak) | `auth`, `settings` | Alternative auth provider: Keycloak OIDC single sign-on. |
| [`permissions`](/modules/permissions) | `auth`, `users` | Role / direct-grant assignment store + admin UI; `RequiresPermission` dependency that honours both forms. |
| [`settings`](/modules/settings) | — | DB-backed key/value store with system / tenant / user precedence; per-module pydantic settings registration; hot reload; `smpy settings` CLI. |
| [`feature_flags`](/modules/feature_flags) | — | Runtime feature toggles with system + tenant overrides. |
| [`file_storage`](/modules/file_storage) | `settings` | Pluggable file storage (filesystem, S3-compatible) with upload validation, presigned URLs, browse/download/delete UI. |
| [`branding`](/modules/branding) | `settings`, `file_storage` | Admin-configurable app identity — app name, logo, favicon and primary colour — pushed to every page via Inertia shared props. |
| [`background_tasks`](/modules/background_tasks) | `users` | Celery + Redis workers, persistent task history, retry, stuck-task sweep, live worker dashboard. |
| [`audit_log`](/modules/audit_log) | `users` | Automatic field-level audit trail for SQLModel entities, with an admin UI to browse change history. |
| [`dashboard`](/modules/dashboard) | `users` | Authenticated landing page with system overview (user counts, module list, health checks). |
| [`site_lock`](/modules/site_lock) | `settings`, `auth` | Optional site-wide shared-password gate for staging / pre-launch sites. Off by default. |

## How modules are wired in

Every module declares an entry point in its `pyproject.toml`:

```toml
[project.entry-points.simple_module]
users = "users.module:UsersModule"
```

At boot, `simple_module_core.discovery.discover_modules()` loads them, sorts them topologically by `ModuleMeta.depends_on`, and the host invokes their lifecycle hooks in order — see [discovery](/framework/discovery) and [lifecycle hooks](/framework/lifecycle).

## What each page covers

- **`ModuleMeta`** — exact `name`, `route_prefix`, `view_prefix`, `depends_on`.
- **Routes** — REST (`/api/...`) + Inertia view (`/...`) endpoints, with the permission each requires.
- **Public contracts** — DTOs and protocols other modules import from `<module>/contracts/`.
- **Models** — SQLModel tables the module owns.
- **Settings** — DB-backed and bootstrap (`SM_*`) fields.
- **Permissions / menu / events / tasks / CLI** — anything the module registers or exposes.
- **Inertia pages** — what's under `pages/*.tsx`.

If a section isn't applicable to a given module, the page omits it.

## Disabling a bundled module

Set `SM_MODULES_ENABLED` to a comma-separated allow-list; only those modules load. Useful when you don't need (say) `background_tasks` and don't want to run Redis:

```bash
SM_MODULES_ENABLED=users,permissions,settings,dashboard
```

Don't drop `users` unless you've replaced authentication with a different module — most other bundled modules rely on it for `request.state.user`.

## Next steps

- [Your first module](/guide/first-module) — build one of your own using the same conventions.
- [Module authoring](/module-authoring) — package and distribute a module via PyPI.
- [Framework / Discovery](/framework/discovery) — how the framework finds installed modules at boot.

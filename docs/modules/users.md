# users

The default auth provider + user-management module: email/password login, OAuth/OIDC sign-in, sessions, registration, invites, password reset, email verification, role assignment, admin UI, and mailer backends. It registers a `UsersAuthProvider` on `app.state.auth.auth_provider`, which the [`auth`](/modules/auth) module's `AuthMiddleware` delegates to for `request.state.user`. (It's one of two bundled auth providers — [`keycloak`](/modules/keycloak) is the alternative; install exactly one.)

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Users` |
| `route_prefix` | `/api/users` |
| `view_prefix` | `/users` |
| `depends_on` | `["Auth"]` |

## Auth flow

The module is built on [`fastapi-users`](https://fastapi-users.github.io/) for password hashing, registration, password reset, and verification. On top of that it layers:

- A signed session cookie (`sm_auth` by default) — the auth module's `AuthMiddleware` calls `UsersAuthProvider.resolve_user`, which reads it on every request and populates `request.state.user`. Bearer tokens (`Authorization: Bearer <token>`) resolve against `users_access_token`.
- OAuth / OIDC sign-in (Google, GitHub, Microsoft/Entra ID, and any generic OIDC provider) — see [OAuth providers](#oauth-providers).
- An invite flow — admins generate an invite link; the recipient sets their password via `POST /api/users/auth/accept-invite`.
- `LoginRateLimiter` — N failures within a window triggers a cooldown per `email::ip` key.
- `ThroughputLimiter` — per-IP rate limit across register / forgot-password / accept-invite / verify-token endpoints.

### Auth endpoints

| Method + path | Body | Notes |
|---|---|---|
| `POST /api/users/auth/login` | `OAuth2PasswordRequestForm` | sets `sm_auth` cookie + `session["user_id"]`; rate-limited per email |
| `POST /api/users/auth/register` | `UserCreate` | gated by `users.allow_signup`; rate-limited |
| `POST /api/users/auth/forgot-password` | `PasswordReset` | rate-limited |
| `POST /api/users/auth/reset-password` | `{token, password}` | |
| `POST /api/users/auth/request-verify-token` | `RequestVerifyToken` | rate-limited |
| `POST /api/users/auth/verify` | `VerifyRequest` | |
| `POST /api/users/auth/accept-invite` | `AcceptInviteRequest` | sets password + signs the user in |
| `GET /api/users/auth/{provider}/login` | — | OAuth: redirect to the IdP (`provider` ∈ configured set) |
| `GET /api/users/auth/{provider}/callback` | `?code=&state=` | OAuth: find-or-create user, set cookie, 303 to `login_redirect_url` |

### Self-service endpoints

| Method + path | Body / response | Permission |
|---|---|---|
| `GET /api/users/me` | → `UserRead` | active user |
| `PATCH /api/users/me` | `SelfProfileUpdate` → `UserRead` | active user |

### Admin endpoints (`users.manage`)

| Method + path | Body / response |
|---|---|
| `GET /api/users/admin` | `?q=&status=&role=&verified=&sort=&order=&page=&per_page=` → `list[UserListItem]` |
| `POST /api/users/admin/invite` | `UserInvite` → `UserListItem` |
| `POST /api/users/admin/{user_id}/disable` | → `UserListItem` |
| `POST /api/users/admin/{user_id}/enable` | → `UserListItem` |
| `POST /api/users/admin/{user_id}/roles` | `RoleAssignment` |
| `POST /api/users/admin/{user_id}/mark-verified` | → `UserListItem` |
| `POST /api/users/admin/{user_id}/reset-password-link` | → `PasswordResetLink` |

### View routes

Public:

- `GET /users/login` → `Users/Login` (shows dev-account buttons in dev)
- `POST /users/logout` → 303 redirect, clears cookie
- `GET /users/register` → `Users/Register` (404 if signup disabled)
- `GET /users/forgot-password` → `Users/ForgotPassword`
- `GET /users/reset-password` → `Users/ResetPassword`
- `GET /users/verify` → `Users/VerifyEmail`
- `GET /users/invite/accept` → `Users/AcceptInvite`

Authenticated:

- `GET /users/me` → `Users/Profile`
- `PATCH /users/me` → form action (redirects)

Admin (`users.manage`):

- `GET /users/admin` → `Users/Users/Index`
- `GET /users/admin/invite` → `Users/Users/Invite`
- `GET /users/admin/{user_id}/edit` → `Users/Users/Edit`

## Public contracts

```python
from users.contracts import (
    UserRead, UserCreate, UserUpdate, UserInvite,
    UserListItem, RoleListItem, RoleAssignment,
    AcceptInviteRequest, PasswordResetLink, SelfProfileUpdate,
)
from users.contracts.events import (
    UserRegistered, UserInvited, UserDisabled, RoleAssigned,
)
```

| Class | Purpose |
|---|---|
| `UserRead` | `id`, `email`, `is_active`, `is_superuser`, `is_verified`, `full_name`, `tenant_id`, `disabled_at`, `last_login_at`. |
| `UserListItem` | Admin list row with `roles`. |
| `RoleListItem` | `id`, `name`, `description`, `user_count`. |
| `UserRegistered`, `UserInvited`, `UserDisabled`, `RoleAssigned` | Events — see [Events](#events). |

## Models

`User` (table `users_user`)

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `email` | `str` | unique, indexed; functional index on `lower(email)` |
| `hashed_password` | `str` | |
| `is_active` / `is_superuser` / `is_verified` | `bool` | |
| `full_name` | `str \| None` | |
| `tenant_id` | `str \| None` | indexed; only set when multi-tenant |
| `disabled_at` | `datetime \| None` | |
| `last_login_at` | `datetime \| None` | indexed |
| `roles` | relationship → `Role` via `UserRole` | eagerly loaded by `AuthMiddleware` |

`Role` (table `users_role`) — `id`, `name` (unique, indexed), `description`.

`UserRole` (table `users_user_role`) — composite-PK join table with `assigned_at`, `assigned_by`. The `(user_id, role_id)` PK is user-id-first; a separate index covers reverse lookups by `role_id`.

`UserAccessToken` (table `users_access_token`) — bearer API tokens; resolved by `UsersAuthProvider` on `Authorization: Bearer` requests (sessions remain the primary browser auth).

`OAuthAccount` (table `users_oauth_account`) — linked OAuth/OIDC accounts: `oauth_name`, `account_id`, `account_email`, `access_token`, `refresh_token`, `expires_at`.

`RefreshToken` (table `users_refresh_token`) — opaque refresh tokens for the bearer flow: `token` (PK), `user_id`, `created_at`, `expires_at`, `revoked_at`.

Two pre-seeded roles get fixed UUIDs so other modules can reference them safely:

| Role | UUID | Default permissions |
|---|---|---|
| `admin` | `00000000-0000-0000-0000-000000000001` | implicitly all (admin bypass in `RequiresPermission`) |
| `user` | `00000000-0000-0000-0000-000000000002` | `users.self.profile`, `file_storage.{upload,download,delete}` |

## Settings

DB-backed via `register_module_settings`. Two values are read **only** from the env at module import time because they bootstrap token signing before the DB is reachable:

| Env var | Default | Purpose |
|---|---|---|
| `SM_USERS_RESET_PASSWORD_TOKEN_SECRET` | `dev-reset-token-secret-change-me` | password-reset token signing |
| `SM_USERS_VERIFICATION_TOKEN_SECRET` | `dev-verify-token-secret-change-me` | email-verify token signing |

Both **must** be replaced with non-placeholder values in production — the boot-time check refuses to start otherwise.

Everything else is DB-backed (initial values are pydantic defaults; edit at `/settings/modules/users`):

| Field | Default |
|---|---|
| `allow_signup` | `False` |
| `require_verification` | `True` |
| `login_redirect_url` | `"/dashboard/"` (if the Dashboard module isn't installed, auto-falls back to the first other module that exposes view routes, or `/` only as a last resort) |
| `reset_password_token_lifetime_seconds` | `3600` |
| `verification_token_lifetime_seconds` | `604_800` (7 days) |
| `bearer_token_lifetime_seconds` | `900` (15 min) |
| `refresh_token_lifetime_seconds` | `2_592_000` (30 days) |
| `cookie_name` | `"sm_auth"` |
| `cookie_max_age_seconds` | `1_209_600` (14 days) |
| `cookie_secure` | `True` (flipped to `False` in dev at startup) |
| `cookie_samesite` | `"lax"` |
| `mailer` | `"console"` (or `"smtp"`) |
| `base_url` | `"http://localhost:8000"` |
| `smtp_host` / `smtp_port` / `smtp_username` / `smtp_password` / `smtp_from` / `smtp_tls` | SMTP config when `mailer="smtp"` |
| `login_rate_limit_failures` | `5` |
| `login_rate_limit_window_seconds` | `300` |
| `login_rate_limit_cooldown_seconds` | `900` |
| `auth_rate_limit_attempts` | `10` |
| `auth_rate_limit_window_seconds` | `300` |
| `bootstrap_email`, `bootstrap_password`, `bootstrap_user_email`, `bootstrap_user_password` | `""` — see [Bootstrap](#bootstrap-the-first-admin) |
| `oauth_google_client_id` / `oauth_google_client_secret` | `""` — Google OAuth |
| `oauth_github_client_id` / `oauth_github_client_secret` | `""` — GitHub OAuth |
| `oauth_microsoft_client_id` / `oauth_microsoft_client_secret` / `oauth_microsoft_tenant` | `""` / `""` / `"common"` — Microsoft (Entra ID) |
| `oauth_oidc_client_id` / `oauth_oidc_client_secret` / `oauth_oidc_discovery_url` / `oauth_oidc_display_name` | `""` / `""` / `""` / `"OIDC"` — generic OIDC |

## Permissions

| Code | Purpose |
|---|---|
| `users.manage` | admin: list / invite / disable / role-assign |
| `users.self.profile` | edit own profile (granted to `user` role) |

## Menu

| Label | URL | Icon | Section | Group | Order | Roles |
|---|---|---|---|---|---|---|
| `Users` | `/users/admin` | `users` | `SIDEBAR` | `Administration` | `100` | `["admin"]` |
| `Profile` | `/users/me` | `user` | `USER_DROPDOWN` | — | `990` | _logged-in_ |
| `Logout` | `/users/logout` (POST) | `log-out` | `USER_DROPDOWN` | — | `999` | _logged-in_ |

## Events

| Event | Fields | Fired |
|---|---|---|
| `UserRegistered` | `user_id`, `email` | on signup |
| `UserInvited` | `user_id`, `email`, `invited_by` | on admin invite |
| `UserDisabled` | `user_id` | on admin disable |
| `RoleAssigned` | `user_id`, `role_name` | once per role on `POST /admin/{user_id}/roles` |

## CLI

- `smpy users create-admin --email <e> --password <p> [--full-name <name>] [--force]` — creates (or, with `--force`, updates) an admin user. Idempotent: re-running with the same email is a no-op without `--force`.

```bash
uv run smpy users create-admin --email admin@example.com --password changeme
```

Programmatically:

```python
from users.bootstrap import create_admin

result = await create_admin(db, email="admin@example.com", password="...")
# result.user, result.created -> bool
```

## Bootstrap (the first admin)

Two paths to seed the first admin:

1. **CLI** — `smpy users create-admin ...`.
2. **Env vars** — set `SM_USERS_BOOTSTRAP_EMAIL` + `SM_USERS_BOOTSTRAP_PASSWORD` before first `make dev`. `bootstrap_admin_from_env(app)` runs at startup and creates the admin if the `users_user` table is empty. Optionally seed a non-admin too via `SM_USERS_BOOTSTRAP_USER_EMAIL` + `SM_USERS_BOOTSTRAP_USER_PASSWORD`.

## Mailer backends

`mailer/` ships two implementations of the `Mailer` protocol:

| Backend | When to use | Configured via |
|---|---|---|
| `ConsoleMailer` | dev — prints invite / verify / reset links to stdout | `mailer="console"` |
| `SmtpMailer` | prod — talks SMTP | `mailer="smtp"` + `smtp_*` settings |

`build_mailer(settings)` returns the right instance based on `users.mailer`.

## OAuth providers

OAuth/OIDC sign-in is **DB-settings-driven**: a provider is enabled simply by setting its `client_id` + `client_secret` (and, for generic OIDC, a discovery URL) in the settings UI at `/settings/modules/users`. No code change or restart — `register_event_handlers` rebuilds the client cache (`app.state.users.oauth_clients`) on the `SettingsReloaded` event, so changes take effect live. Providers with no credentials are silently skipped.

Built-in provider keys (the `{provider}` URL segment):

| Provider | Key | Notes |
|---|---|---|
| Google | `google` | |
| GitHub | `github` | |
| Microsoft (Entra ID) | `microsoft` | `oauth_microsoft_tenant`: `"common"` (any account), `"organizations"` (work/school), or a tenant GUID |
| Generic OIDC | `oidc` | any provider exposing a discovery URL (Keycloak, Authentik, Auth0, Zitadel, …); discovery failure logs + disables rather than breaking boot |

A single dispatcher pair (`/api/users/auth/{provider}/login` + `/callback`) serves every provider; the client is resolved per request from the cache. The `/callback` returns a 303 redirect (not the stock fastapi-users 204) so Inertia lands on a real page, with the auth cookie attached. Find-or-create + email association goes through `UserManager.oauth_callback` (`associate_by_email=True`, `is_verified_by_default=True`); state CSRF uses the signed session cookie. Linked accounts are stored in `users_oauth_account`.

## UsersAuthProvider

`UsersAuthProvider` (registered on `app.state.auth.auth_provider` in `register_settings`) is the `AuthProvider` the auth module's `AuthMiddleware` delegates to. On each request `resolve_user`:

- For a `Bearer` token, looks the token up in `users_access_token` and returns the active user.
- Otherwise reads `session["user_id"]`, returns the cached context from `session["user_ctx"]` on a hit, else loads the User row with eagerly-loaded roles, builds a `UserContext`, caches it in `session["user_ctx"]`, and clears stale session keys when the user is missing/disabled.

`get_login_url()` → `/users/login`, `get_logout_url()` → `/users/logout`. The provider's `get_public_paths()` declares these prefixes anonymous (in addition to the framework defaults `/health`, `/static/`, `/api/docs`, `/api/redoc`, `/openapi.json`, `/i18n/`, `/`):

`/users/login`, `/users/register`, `/users/forgot-password`, `/users/reset-password`, `/users/verify`, `/users/invite/accept`, `/api/users/auth/`, `/api/users/register`.

Anything else without a session redirects to `/users/login` (or returns 401 JSON for `/api/*` / bearer requests).

## Roles cache

`roles_cache.py` keeps an in-memory list of `RoleSummary(id, name)` on `app.state.users.roles_cache`. Refreshed at startup and on demand via `refresh_roles_cache(app)`. Used by the admin UI to render role pickers without hitting the DB on every request.

## Inertia pages

Auth flow:
- `Users/Login.tsx`, `Users/Register.tsx`, `Users/ForgotPassword.tsx`, `Users/ResetPassword.tsx`, `Users/VerifyEmail.tsx`, `Users/AcceptInvite.tsx`, `Users/Profile.tsx`.

Admin:
- `Users/Users/Index.tsx`, `Users/Users/Invite.tsx`, `Users/Users/Edit.tsx`.

Components:
- `Users/components/IndexFilters.tsx`, `Users/components/RolesTab.tsx`.

## Notes

- `cookie_secure` is automatically flipped to `False` in dev (`SM_ENVIRONMENT=development`) so login works over plain HTTP. Don't override it in non-dev environments.
- `LoginRateLimiter` keys login attempts by `lowercased-email::client-ip`. Counters live in-process (no Redis), so a multi-worker deployment has independent counters per worker — swap for a Redis-backed store when running more than one worker.
- The functional `lower(email)` index makes case-insensitive lookups fast on Postgres; on SQLite the lookup falls back to `LOWER(email) = ?` which still uses the regular index.

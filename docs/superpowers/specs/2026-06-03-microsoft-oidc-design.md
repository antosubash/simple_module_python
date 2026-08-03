# Microsoft (Entra ID) OAuth — DB-settings-driven, hot-reloadable providers

**Date:** 2026-06-03
**Status:** Approved (design)
**Module:** `users`

## Summary

Add a first-class `microsoft` OAuth provider (Microsoft Entra ID / Microsoft
accounts) to the `users` module, alongside the existing Google, GitHub, and
generic-OIDC providers. As part of the same change, move **all** OAuth provider
configuration off environment variables onto the DB-backed settings UI
(`/settings/modules → Users`) with **live reload**, and fix a latent
inconsistency in how providers are wired today.

## Background — why this is more than "add one provider"

The OAuth plumbing is already provider-agnostic at the transport layer
(`users/oauth/api.py` mounts a `/login` + `/callback` pair per provider;
find-or-create flows through `UserManager.oauth_callback`). Adding a named
provider is normally a two-branch change in `users/oauth/providers.py`.

The requirement here is that Microsoft be configured through the **admin
settings UI**, not env vars. That collides with a structural detail:

- **Routes mount at app *construction*.** `UsersModule.register_routes`
  (`create_app` step 9) calls `register_oauth_routes(api_router,
  UsersSettings())`. That fresh `UsersSettings()` only carries values captured
  by `env_str()` at import time — DB settings have **not** been hydrated yet
  (hydration runs later, in the lifespan, before `on_startup`).
- **Buttons mount at *startup*.** `on_startup` sets
  `state.oauth_providers = enabled_provider_names(s)` from the **hydrated**
  settings.

Consequence: a provider configured **only via the settings UI** today renders a
login button (startup reads hydrated settings) whose route was **never mounted**
(construction read empty env defaults) → the button 404s. The existing
Google/GitHub/OIDC providers only work because their credentials arrive via env
and are captured at import time. `requires_restart=True` cannot paper over this:
a restart re-runs `register_routes` before hydration again, so DB-only
credentials remain invisible at mount time.

Therefore, to support DB-settings-driven providers at all, the route layer must
resolve providers at **request time** from hydrated settings. We do this for
**all** providers (not just Microsoft) so the system stays consistent and the
latent button-404 bug is fixed everywhere. This mirrors the migration
`background_tasks` already made (its settings stopped reading `SM_BG_TASKS_*`
env vars; values now come from DB hydration).

## Goals

1. `microsoft` provider usable end-to-end (login button → IdP → callback →
   find-or-create user → session).
2. All OAuth providers configured via the settings UI, with credentials masked.
3. Provider changes take effect **without a process restart** (live reload via
   the existing `SettingsReloaded` event).
4. No new DB tables or migrations.

## Non-goals (YAGNI)

- No token-refresh / offline-access flow.
- No provider logos/icons on buttons (matches current text buttons).
- No PKCE changes (the Microsoft client already sets `response_mode=query`).
- No change to the find-or-create / cookie / redirect semantics in the callback.

## Design

### 1. Settings — `modules/users/users/settings.py`

Add Microsoft fields as plain `Field` (no `env_str`), grouped for the admin UI:

```python
_MS_OAUTH = {"group": "Microsoft OAuth"}
oauth_microsoft_client_id: str = Field(default="", json_schema_extra=_MS_OAUTH)
oauth_microsoft_client_secret: str = Field(default="", json_schema_extra=_MS_OAUTH)  # auto-masked
oauth_microsoft_tenant: str = Field(default="common", json_schema_extra=_MS_OAUTH)
```

- Migrate the existing `oauth_google_*`, `oauth_github_*`, `oauth_oidc_*` fields
  off `env_str(...)` → plain `Field(default=...)`, adding `group` metadata
  (`"Google OAuth"`, `"GitHub OAuth"`, `"OIDC"`). Secret-bearing fields
  (`*_client_secret`) auto-mask via `is_secret_field` (matches `secret`).
- **Leave the two token-secret fields (`reset_password_token_secret`,
  `verification_token_secret`) on `env_str`** — they are a deliberate bootstrap
  path (the `@model_validator` must be satisfiable before any DB-backed setting
  can be seeded). Untouched.
- Rewrite the stale comment that claims OAuth secrets are env-only "because
  admins can read the DB settings table" — secrets are masked in the UI
  (`••••••••`), the same treatment the SMTP password already gets.
- **No `requires_restart`** on any OAuth field: the route layer becomes live.

**Tenant default:** `common` (httpx_oauth default — any work/school *or*
personal Microsoft account). Configurable per deployment; operators lock down
to their org by setting the tenant to their tenant GUID or `organizations`.
Documented as a security note.

### 2. Provider construction — `modules/users/users/oauth/providers.py`

- Add a `microsoft` branch to `build_clients()`:

  ```python
  from httpx_oauth.clients.microsoft import MicrosoftGraphOAuth2

  MicrosoftGraphOAuth2(
      settings.oauth_microsoft_client_id,
      settings.oauth_microsoft_client_secret,
      tenant=settings.oauth_microsoft_tenant or "common",
      name="microsoft",
  )
  ```
  Gated on `client_id and client_secret` being set.
- **Remove `enabled_provider_names()`.** The login-button list is now derived
  from the successfully-built client map, so a provider only gets a button if
  its client actually constructed (fixes the case where OIDC discovery fails but
  a button still shows).
- Add `build_client_map(settings) -> dict[str, OAuthProvider]` (thin wrapper:
  `{p.name: p for p in build_clients(settings)}`) for O(1) request-time lookup.

`OAuthProvider` (NamedTuple: `name`, `display_name`, `client`) is unchanged.

### 3. Route dispatcher — `modules/users/users/oauth/api.py`

Replace the N per-provider routers with **one** provider-agnostic pair, mounted
unconditionally:

- `GET /auth/{provider}/login`
- `GET /auth/{provider}/callback` (route name `users_oauth_callback`)

Behaviour:

- Resolve the client at **request time**: `provider_obj =
  request.app.state.users.oauth_clients.get(provider)`; if `None` → `404`.
- Callback URL: `request.url_for("users_oauth_callback", provider=provider)`
  (Starlette `url_for` with a path param) — used identically in `/login` (to
  pass to the IdP) and `/callback` (token exchange).
- State CSRF: unchanged mechanism — `secrets.token_urlsafe(32)` stashed under
  the per-provider session key `oauth_state:{provider}`, compared with
  `compare_digest`.
- Everything from `get_access_token` → `get_id_email` → `oauth_callback` →
  cookie → 303 redirect to `login_redirect_url` is **unchanged**.

`register_oauth_routes(api_router)` no longer takes `settings` and always mounts
the single dispatcher.

### 4. Cache lifecycle — `modules/users/users/module.py` + `state.py`

- `UsersState`: add `oauth_clients: dict[str, OAuthProvider] =
  field(default_factory=dict)` (default empty so request handlers and tests that
  skip `on_startup` see an empty map, not `AttributeError`).
- `register_routes`: mount the dispatcher unconditionally; **drop** the
  pre-hydration `settings = UsersSettings()` block (it existed only to feed the
  old route builder).
- `on_startup`: build the cache and derive the button list from the **hydrated**
  settings `s`:
  ```python
  state.oauth_clients = build_client_map(s)
  state.oauth_providers = [
      {"name": p.name, "display_name": p.display_name} for p in state.oauth_clients.values()
  ]
  ```
- Override `register_event_handlers(self, bus, app)`: subscribe to
  `SettingsReloaded`; when `event.package == "users"`, rebuild `oauth_clients`
  and `oauth_providers` from `app.state.users.settings`. → providers can be
  added/removed live with no restart. `SettingsReloaded` is imported from
  `settings.contracts.events` (plugin→plugin import; `users` already depends on
  the `settings` module via `register_module_settings`).

### 5. Frontend — no change

`Login.tsx` already maps `oauth_providers` → outline buttons linking to
`/api/users/auth/{name}/login`. A "Microsoft" button appears automatically once
configured. The login view (`users/auth_local/views.py`) reads
`request.app.state.users.oauth_providers` per request, so a live cache rebuild
is reflected on the next page load.

## Identity mapping & documented caveat

`MicrosoftGraphOAuth2.get_id_email` returns `(profile["id"],
profile["userPrincipalName"])` from Graph `/me`. For tenant members,
`userPrincipalName` equals the email. For **guest/external** accounts the UPN is
not a clean email (e.g. `user_ext.com#EXT#@tenant.onmicrosoft.com`), and that
string becomes the local `account_email`. We use the stock client and **document
this limitation** rather than overriding `get_id_email` (consistent with using
the upstream client for Google/GitHub).

## Data / migrations

None. `OAuthAccount.oauth_name` is already `str(max_length=100)` — `"microsoft"`
fits with no schema change. Settings overrides persist in the settings module's
existing store table.

## Testing — `modules/users/tests/test_oauth.py` (+ additions)

- `build_clients` / `build_client_map` include `microsoft` when configured;
  carry the right `client_id`; the tenant is reflected in the client's authorize
  URL; provider skipped when the secret is missing.
- Dispatcher: a configured provider redirects (302) from `/login`; an unknown /
  unconfigured `{provider}` returns `404`.
- `SettingsReloaded(package="users")` handler rebuilds the cache: a provider not
  present at boot appears after reload; a provider whose credentials are cleared
  disappears.
- Update / remove tests that referenced `enabled_provider_names`.
- Existing Google/GitHub `build_clients` and `oauth_callback` find-or-create /
  email-association tests continue to pass unchanged.

Network-hitting paths (real token exchange, Graph profile fetch) remain out of
automated coverage, consistent with the existing test file's stated policy;
validated in a manual QA pass against a dev IdP.

## Docs

- `modules/users/README.md`: add a "Social / Microsoft sign-in" section —
  configure at **/settings/modules → Users → Microsoft OAuth**; redirect URI is
  `<base>/api/users/auth/microsoft/callback`; tenant guidance (`common` vs
  tenant GUID / `organizations`); note that the secret is masked in the UI.
- Note the env→DB migration for existing Google/GitHub/OIDC deployments: run
  `smpy settings import-from-env` once (maps `SM_USERS_OAUTH_*` → fields).
- Document the UPN-isn't-always-email caveat for guest accounts.
- Release notes: call out that OAuth credentials are no longer read from
  `SM_USERS_OAUTH_*` env vars at runtime — use the settings UI or
  `import-from-env`.

## Risks

- **Behaviour change for env-configured deployments.** Dropping `env_str` from
  Google/GitHub/OIDC means `SM_USERS_OAUTH_*` env vars are no longer read at
  runtime. Mitigation: `smpy settings import-from-env` (the same path
  `background_tasks` used) + release-notes callout.
- **OIDC discovery timing.** Discovery moves from construction to
  `on_startup`/on-reload. Equivalent boot-time cost; failures still degrade
  gracefully (`OpenIDConfigurationError` caught → provider dropped from the
  map, so no button and a 404 route rather than a boot failure).
- **`url_for` with path param** must produce the exact callback URL registered
  with the IdP; covered by the dispatcher test and manual QA.

## Files touched

- `modules/users/users/settings.py` — Microsoft fields; migrate OAuth fields off
  `env_str`; `group` metadata; comment rewrite.
- `modules/users/users/oauth/providers.py` — `microsoft` branch; remove
  `enabled_provider_names`; add `build_client_map`.
- `modules/users/users/oauth/api.py` — single request-time dispatcher.
- `modules/users/users/oauth/__init__.py` — exports.
- `modules/users/users/state.py` — `oauth_clients` field.
- `modules/users/users/module.py` — unconditional mount; `on_startup` cache
  build; `register_event_handlers` reload.
- `modules/users/tests/test_oauth.py` — updated + new tests.
- `modules/users/README.md` — provider setup docs.
- Release notes — env→DB migration callout.

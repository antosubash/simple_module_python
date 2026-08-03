# keycloak

A pluggable **OIDC auth provider** backed by Keycloak. Install it *instead of* [`users`](/modules/users) to delegate identity — login, users, and roles — to Keycloak. Browser users are redirected to Keycloak's hosted login; API/mobile clients send a `Bearer` access token that the module validates against Keycloak's JWKS.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Keycloak` |
| `route_prefix` | `/api/keycloak` |
| `view_prefix` | `/keycloak` |
| `depends_on` | `["Auth", "Settings"]` |

The module sets the class flag `_is_auth_provider = True`, which is what the auth-provider diagnostics count (see [below](#auth-provider-diagnostics)).

## The AuthProvider contract

`keycloak` implements the [`auth`](/modules/auth) module's `AuthProvider` protocol (`auth.contracts.provider.AuthProvider`). The contract is:

```python
@runtime_checkable
class AuthProvider(Protocol):
    name: str

    async def resolve_user(self, request: Request) -> UserContext | None: ...
    def get_login_url(self, request: Request, next_url: str | None = None) -> str: ...
    def get_logout_url(self, request: Request) -> str: ...
    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]: ...
    def is_bearer_request(self, request: Request) -> bool: ...
```

`KeycloakAuthProvider` (`name = "keycloak"`) registers itself on `app.state.auth.auth_provider` during `register_settings`. Exactly one module — `users` *or* `keycloak`, not both — may do this.

### Slotting into the principal-resolver chain

The provider-agnostic `AuthMiddleware` (in `auth`) runs on every request and:

1. Calls `provider.resolve_user(request)`. The Keycloak provider:
   - If there's an `Authorization: Bearer <token>` header, validates the JWT against the cached JWKS and maps claims → `UserContext`.
   - Otherwise rehydrates `UserContext.from_session_dict(...)` from the browser session cookie (populated by the OIDC callback).
2. If the provider returns `None`, it falls through to the registered **principal resolvers** (`app.state.auth.principal_resolvers`), trying each until one matches.
3. If still unresolved and the path isn't public: `/api/*` and bearer requests get a `401` JSON; browser requests are redirected to `provider.get_login_url(...)` (`/keycloak/login`), with the original URL stashed in the session as `next`.

`get_public_paths()` exempts `/keycloak/login`, `/keycloak/logout`, and `/api/keycloak/auth/` from auth.

## Bearer-token validation

`JWKSCache` (`keycloak/jwks.py`) caches Keycloak's RS256 public signing keys (`/realms/<realm>/protocol/openid-connect/certs`) and validates tokens with PyJWT, checking signature, `issuer`, and `audience` (the `client_id`). It refetches once on a cache miss / unknown `kid`, so Keycloak key rotation is handled gracefully. The cache is built in `on_startup` (only when `server_url` and `realm` are configured) and attached to the provider.

On a valid bearer token the provider upserts a `KeycloakUserCache` row keyed by the Keycloak `sub`, so each external identity maps to a stable framework UUID, then returns a `UserContext` whose `id` is that UUID.

## Browser login flow (OIDC)

`OIDCClient` (`keycloak/oidc.py`) wraps the realm's authorization-code endpoints.

| Method + path | What |
|---|---|
| `GET /keycloak/login` | Inertia `Keycloak/Login` page (auto-redirects to the IdP). |
| `POST /keycloak/logout` | Clears the session, redirects to Keycloak's RP-initiated logout (`post_logout_redirect_uri` back to `/keycloak/login`, with `id_token_hint`). |
| `GET /api/keycloak/auth/login` | Builds the authorization URL (random `state` + `nonce` stored in session) and 302s to Keycloak. |
| `GET /api/keycloak/auth/callback` | Verifies `state`, exchanges the `code` for tokens, validates the access token, upserts the user cache, writes `UserContext` + the id token to the session, then redirects to `next` (or `login_redirect_url`). |

## Settings

DB-backed via `register_module_settings("keycloak", KeycloakSettings, ...)`; bootstrap defaults come from `SM_KEYCLOAK_*` env vars. State lives at `app.state.keycloak` (`KeycloakState`: `settings`, `jwks_cache`).

| Field | Env var | Default | Notes |
|---|---|---|---|
| `server_url` | `SM_KEYCLOAK_SERVER_URL` | `""` | Keycloak base URL |
| `realm` | `SM_KEYCLOAK_REALM` | `""` | realm name |
| `client_id` | `SM_KEYCLOAK_CLIENT_ID` | `""` | also the expected JWT audience |
| `client_secret` | `SM_KEYCLOAK_CLIENT_SECRET` | `""` | confidential-client secret |
| `roles_claim_path` | — | `"realm_access.roles"` | dotted path to the roles array in the token |
| `admin_role` | — | `"admin"` | |
| `login_redirect_url` | — | `"/dashboard/"` | post-login landing |
| `jwks_cache_ttl_seconds` | — | `3600` | signing-key cache TTL |
| `role_mapping` | — | `{"admin": "admin", "user": "user"}` | Keycloak realm role → framework permission/role |

`server_url`, `realm`, `client_id`, and `client_secret` are **required in production** — `KeycloakSettings` raises at boot if any is missing outside a non-prod environment. They may be left blank in development and filled in later through the settings admin UI.

### Role mapping

`role_mapping` translates Keycloak realm roles (read from `roles_claim_path`) into the framework's role names. Roles the user has that aren't in the mapping are dropped, so only explicitly mapped roles reach the `UserContext`.

## Models

`KeycloakUserCache` (table `keycloak_user_cache`)

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK; the stable framework user id |
| `keycloak_sub` | `str` | unique, indexed; the Keycloak `sub` claim |
| `email` | `str` | from the token |
| `full_name` | `str \| None` | from `preferred_username` |
| `last_login_at` | `datetime \| None` | refreshed on each resolve |

## Menu

| Label | URL | Icon | Section | Order | Method |
|---|---|---|---|---|---|
| `Logout` | `/keycloak/logout` | `log-out` | `USER_DROPDOWN` | `999` | `post` |

## Inertia pages

- `Keycloak/Login.tsx` — the "redirecting to identity provider" splash.
- `Keycloak/LoggedOut.tsx` — post-logout confirmation.

## Locales

Top-level keys in `keycloak/locales/en.json` (namespace `keycloak`): `login`, `logout`, `errors`.

## Auth-provider diagnostics

The framework's module diagnostics (run by `make doctor` and at prod boot) count modules with `_is_auth_provider = True`:

- **SM020** (error) — more than one auth provider installed (e.g. `users` *and* `keycloak`). Install only one.
- **SM021** (warning) — no auth provider installed at all.

In production these errors fail boot. So swapping to Keycloak means **removing `simple_module_users`** from the host's dependencies, not running it alongside.

## Enabling

Add the package to the host instead of `simple_module_users`:

```toml
dependencies = [
    "simple_module_keycloak==0.0.17",
]
```

Then `uv sync --all-packages`. The entry point (`keycloak = "keycloak.module:KeycloakModule"`) is discovered automatically; set the four `SM_KEYCLOAK_*` env vars (or configure them via the settings admin UI after first boot). It depends on the [`auth`](/modules/auth) and [`settings`](/modules/settings) modules.

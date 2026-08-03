# Pluggable Auth: AuthProvider Contract + Keycloak Module

**Date:** 2026-05-27
**Status:** Design — approved for implementation planning
**Builds on:** [2026-05-21 Auth principal-resolver chain](2026-05-21-auth-principal-resolver-design.md) (must land first)

## Goal

Make the framework's authentication layer swappable. Framework users install either the existing `users` module (local credentials + OAuth) or a new `keycloak` module (Keycloak OIDC) — both implement the same `AuthProvider` contract so every other module is unaffected. Both web and mobile clients are supported regardless of which provider is active.

## Relationship to the Principal-Resolver Spec

The [principal-resolver design](2026-05-21-auth-principal-resolver-design.md) (issue #163) adds the extension point for bearer-token resolution and the 401-JSON-for-API behavior. That spec is a **prerequisite** for this one — it lands the resolver chain and the API-vs-browser response split. This design builds on top:

- The principal-resolver chain becomes one of the tools an `AuthProvider` uses internally (the `users` provider registers its cookie resolver as the primary path and lets downstream modules add PAT resolvers via the chain).
- The `keycloak` provider uses its own `resolve_user` that validates Keycloak JWTs for bearer tokens and reads session for browser flows — it doesn't use the resolver chain for its core flow, but the chain remains available for downstream modules that want to add extra credential types on top of Keycloak (e.g., service-account tokens).
- The 401-JSON-for-`/api/*` behavior from the resolver spec carries forward unchanged.

## Scope

**In scope.**
- `AuthProvider` protocol in `auth/contracts/` — the interface both providers implement.
- Provider-agnostic `AuthMiddleware` extracted from `users/middleware.py` into `auth/`.
- Bearer token transport for mobile clients (framework-issued tokens with `users`, Keycloak-issued JWTs with `keycloak`).
- New `keycloak` module package: OIDC login (web redirect + mobile PKCE), JWT validation against JWKS, role mapping, lightweight user cache table.
- Conflict diagnostic (`SM020`) — boot fails if both `users` and `keycloak` are installed.
- `principal_serializer` registration moved from `users/module.py` into `auth/` so it works with either provider.

**Out of scope.**
- Full OAuth2 authorization server (client registration, scopes, token introspection for third-party apps).
- Keycloak admin API integration (realm/client provisioning from the framework).
- Dual-provider mode (authenticating some users via `users` and others via `keycloak` simultaneously).
- Migration tooling to move existing `users` data into Keycloak.

## Non-goals & invariants

- **`auth` module stays the stable contract layer.** Other modules import only from `auth.contracts` and `auth.deps` — never from `users` or `keycloak` directly.
- **`UserContext` is the single identity type.** Every downstream consumer (menus, permissions, audit listeners, Inertia shared props) operates on `UserContext` regardless of provider.
- **`PermissionRegistry` is framework-owned.** Both providers map their roles into the same registry. Permission definitions live in application modules, not in the identity provider.
- **Session cookie (`session`) stays Starlette-managed.** Both providers use the framework's `SessionMiddleware` for server-side state (redirect targets, OIDC nonces). The auth *credential* transport differs (cookie vs. bearer), but the session layer is shared.

## Architecture

Five pieces, built in dependency order:

### 1. AuthProvider Protocol (in `auth/contracts/provider.py`)

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable
from starlette.requests import Request
from auth.contracts.schemas import UserContext


@runtime_checkable
class AuthProvider(Protocol):
    name: str

    async def resolve_user(self, request: Request) -> UserContext | None:
        """Extract authenticated user from the request.

        For cookie-based providers: read session/cookie, validate, return UserContext.
        For token-based providers: decode Authorization header, validate, return UserContext.
        Returns None if no valid credential is present.
        """
        ...

    def get_login_url(self, request: Request, next_url: str | None = None) -> str:
        """URL to redirect unauthenticated browser requests to."""
        ...

    def get_logout_url(self, request: Request) -> str:
        """URL/endpoint to POST for logout.

        Keycloak needs RP-initiated logout (redirect to Keycloak's /logout).
        Users module clears session + cookie locally.
        """
        ...

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return (prefix_paths, exact_paths) that skip authentication.

        Framework-level paths (/health, /static/, /api/docs, /openapi.json, /i18n/)
        are always public (handled by the middleware itself). Providers return only
        their own paths (e.g., /users/login or /keycloak/login).
        """
        ...

    def is_bearer_request(self, request: Request) -> bool:
        """True if the request carries a bearer token (mobile/API client)."""
        ...
```

Both `users` and `keycloak` modules implement this protocol. The active provider is stored on `app.state.auth_provider` during module registration.

### 2. Provider-Agnostic AuthMiddleware (moved to `auth/`)

The current `users/middleware.py` hardcodes session-key reading and DB user loading. The new middleware delegates to the provider:

```python
_FRAMEWORK_PUBLIC_PREFIXES = (
    "/health",
    "/static/",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
    "/i18n/",
)
_FRAMEWORK_PUBLIC_EXACT = ("/",)


class AuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        provider: AuthProvider = scope["app"].state.auth_provider

        # Framework-level public paths
        is_public = (
            any(path.startswith(p) for p in _FRAMEWORK_PUBLIC_PREFIXES)
            or path in _FRAMEWORK_PUBLIC_EXACT
        )
        # Provider-specific public paths
        if not is_public:
            prefix_paths, exact_paths = provider.get_public_paths()
            is_public = any(path.startswith(p) for p in prefix_paths) or path in exact_paths

        request = Request(scope)
        user_ctx = await provider.resolve_user(request)

        # Fall through to principal-resolver chain (from #163 spec)
        if user_ctx is None:
            resolvers = getattr(scope["app"].state.auth, "principal_resolvers", ())
            for resolver in resolvers:
                try:
                    user_ctx = await resolver(request)
                except Exception:
                    logger.exception("Principal resolver %r raised; treating as no-match", resolver)
                    continue
                if user_ctx is not None:
                    break

        if user_ctx is None and not is_public:
            if path.startswith("/api/"):
                response = JSONResponse({"detail": "Not authenticated"}, status_code=401)
            else:
                session = scope["session"]
                session["next"] = str(request.url)
                response = RedirectResponse(provider.get_login_url(request), status_code=302)
            await response(scope, receive, send)
            return

        if user_ctx is not None:
            request.state.user = user_ctx
            token = current_user_id.set(user_ctx.id)
            try:
                await self.app(scope, receive, send)
            finally:
                current_user_id.reset(token)
            return

        await self.app(scope, receive, send)
```

Key behaviors:
- Bearer requests get `401 JSON` instead of `302 redirect` (from the principal-resolver spec).
- The resolver chain from #163 runs after the provider's own `resolve_user`, so downstream PAT modules work with either provider.
- Framework-level public paths are hardcoded; provider-specific paths come from `get_public_paths()`.

### 3. Users Module Changes

The `users` module adapts to implement `AuthProvider` and gains bearer token support for mobile/API clients.

**`AuthProvider` implementation.** A new `UsersAuthProvider` class in `users/provider.py`:

```python
class UsersAuthProvider:
    name = "users"

    async def resolve_user(self, request: Request) -> UserContext | None:
        # Path 1: Bearer token (mobile/API)
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            return await self._resolve_bearer(request, token)

        # Path 2: Session cookie (browser — existing logic moved here)
        session = request.scope.get("session", {})
        raw_user_id = session.get("user_id")
        if not raw_user_id:
            return None
        # Fast path: cached UserContext in session
        user_ctx = UserContext.from_session_dict(session.get("user_ctx"))
        if user_ctx and user_ctx.id == str(raw_user_id):
            return user_ctx
        # Slow path: DB lookup (existing _load_user logic)
        return await self._load_user_from_db(request, raw_user_id)

    def get_login_url(self, request, next_url=None) -> str:
        return "/users/login"

    def get_logout_url(self, request) -> str:
        return "/users/logout"

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (
            (
                "/users/login",
                "/users/register",
                "/users/forgot-password",
                "/users/reset-password",
                "/users/verify",
                "/users/invite/accept",
                "/api/users/auth/",
                "/api/users/register",
            ),
            (),
        )

    def is_bearer_request(self, request) -> bool:
        return request.headers.get("authorization", "").startswith("Bearer ")
```

**Registration.** `UsersModule.register_settings()` adds:
```python
app.state.auth_provider = UsersAuthProvider()
```

**New: Refresh token support for mobile.** Mobile clients need token refresh without re-authenticating:

- **`RefreshToken` model** — new table `users_refresh_token`: `token` (UUID, PK), `user_id` (FK), `created_at`, `expires_at` (30 days), `revoked_at`.
- **`POST /api/users/auth/token`** — email+password login returning `{access_token, token_type, expires_in, refresh_token}` as JSON (no cookie set).
- **`POST /api/users/auth/token/refresh`** — exchange refresh token for new access + refresh token pair. Old refresh token is revoked (rotation).
- **`DELETE /api/users/auth/token`** — revoke refresh token (mobile logout).
- Access tokens for bearer transport use a shorter lifetime (15 minutes) than cookie tokens (14 days). This is configurable via `UsersSettings.bearer_token_lifetime_seconds`.

**OAuth for mobile.** When `/api/users/oauth/{provider}/callback` receives a request with `Accept: application/json` (or `?response_type=token` query param), it returns tokens as JSON instead of setting cookies and redirecting.

### 4. Keycloak Module (new package)

**Package:** `modules/keycloak/` with entry point `simple_module.keycloak = keycloak.module:KeycloakModule`.

**Depends on:** `Auth` (same dependency as `users`).

**Settings** (`SM_KEYCLOAK_*`, DB-backed after bootstrap):

| Setting | Default | Description |
|---------|---------|-------------|
| `server_url` | (required) | Keycloak base URL (e.g. `https://auth.example.com`) |
| `realm` | (required) | Realm name |
| `client_id` | (required) | OIDC client ID (confidential client) |
| `client_secret` | (required) | OIDC client secret |
| `roles_claim_path` | `realm_access.roles` | Dot-path to extract roles from ID/access token |
| `admin_role` | `admin` | Keycloak role name that maps to framework admin |
| `login_redirect_url` | `/dashboard/` | Where to redirect after successful login |
| `jwks_cache_ttl_seconds` | `3600` | How long to cache Keycloak's public keys |
| `role_mapping` | `{"admin": "admin", "user": "user"}` | Keycloak role → framework role mapping |

**Module layout:**

```
modules/keycloak/keycloak/
├── module.py           # KeycloakModule(ModuleBase) — registers as auth_provider
├── models.py           # KeycloakUserCache table
├── settings.py         # KeycloakSettings
├── provider.py         # KeycloakAuthProvider(AuthProvider) implementation
├── oidc.py             # OIDC discovery, token exchange helpers
├── jwks.py             # JWKS key cache + JWT signature validation
├── endpoints/
│   ├── api.py          # /api/keycloak/auth/login, /callback, /userinfo
│   └── views.py        # /keycloak/login (redirect), /keycloak/logout
├── pages/
│   ├── Login.tsx       # Minimal page that auto-redirects to Keycloak
│   └── LoggedOut.tsx   # Post-logout landing page
└── locales/
    └── en.json
```

**Web login flow:**

1. User hits any protected page → `AuthMiddleware` redirects to `/keycloak/login`.
2. `/keycloak/login` view generates OIDC state + nonce, stores in session, redirects to Keycloak's authorization endpoint: `{server_url}/realms/{realm}/protocol/openid-connect/auth?client_id=...&redirect_uri=/api/keycloak/auth/callback&response_type=code&scope=openid+email+profile&state=...&nonce=...`.
3. User authenticates at Keycloak's hosted login page.
4. Keycloak redirects to `/api/keycloak/auth/callback?code=...&state=...`.
5. Callback validates state against session, exchanges code for tokens via Keycloak's token endpoint.
6. Validates ID token signature (JWKS), checks `iss`, `aud`, `exp`, `nonce`.
7. Extracts claims: `sub`, `email`, `preferred_username` or `name`, `realm_access.roles`.
8. Upserts `KeycloakUserCache` row (maps `keycloak_sub` → stable framework UUID).
9. Maps Keycloak roles to framework roles via `role_mapping` setting.
10. Builds `UserContext`, stores in `session["user_ctx"]`. Stores `id_token` in session for logout.
11. Redirects to `session["next"]` or `login_redirect_url`.

**Mobile login flow (Authorization Code + PKCE):**

Mobile clients authenticate directly with Keycloak — the framework is not in the login path:

1. Mobile app opens system browser to Keycloak's auth endpoint with `code_challenge` + `code_challenge_method=S256` (PKCE).
2. User authenticates at Keycloak.
3. Keycloak redirects to mobile app's registered redirect URI (deep link / custom scheme) with auth code.
4. Mobile app exchanges code + `code_verifier` for tokens directly with Keycloak's token endpoint.
5. Mobile app sends requests to the framework API with `Authorization: Bearer <access_token>`.
6. Framework's `KeycloakAuthProvider.resolve_user()` validates the JWT against Keycloak's JWKS keys.
7. On token expiry, mobile app refreshes directly with Keycloak (`grant_type=refresh_token`). The framework is not involved in token refresh.

**`KeycloakAuthProvider` implementation:**

```python
class KeycloakAuthProvider:
    name = "keycloak"

    def __init__(self, settings: KeycloakSettings, jwks_cache: JWKSCache):
        self.settings = settings
        self.jwks_cache = jwks_cache

    async def resolve_user(self, request: Request) -> UserContext | None:
        # Path 1: Bearer token (mobile/API)
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            claims = await self.jwks_cache.validate_jwt(token)
            if claims is None:
                return None
            return self._claims_to_user_context(claims)

        # Path 2: Session (browser)
        session = request.scope.get("session", {})
        return UserContext.from_session_dict(session.get("user_ctx"))

    def get_login_url(self, request, next_url=None) -> str:
        return "/keycloak/login"

    def get_logout_url(self, request) -> str:
        return "/keycloak/logout"

    def get_public_paths(self):
        return (
            ("/keycloak/login", "/keycloak/logout", "/api/keycloak/auth/"),
            (),
        )

    def is_bearer_request(self, request) -> bool:
        return request.headers.get("authorization", "").startswith("Bearer ")

    def _claims_to_user_context(self, claims: dict) -> UserContext:
        roles_raw = _extract_nested(claims, self.settings.roles_claim_path)
        mapped_roles = [
            self.settings.role_mapping[r]
            for r in (roles_raw or [])
            if r in self.settings.role_mapping
        ]
        return UserContext(
            id=str(self._get_or_create_cache_id(claims["sub"])),
            email=claims.get("email", ""),
            name=claims.get("preferred_username") or claims.get("name", ""),
            roles=mapped_roles,
            tenant_id=claims.get("tenant_id"),
        )
```

**JWT validation (`jwks.py`):**

- Fetches Keycloak's JWKS endpoint (`{server_url}/realms/{realm}/protocol/openid-connect/certs`) on first request.
- Caches keys in memory with configurable TTL (default 1 hour).
- On validation failure with cached keys: refetch JWKS once before rejecting (handles key rotation).
- Validates: signature (RS256), `iss` (must match `{server_url}/realms/{realm}`), `aud` (must contain `client_id`), `exp` (not expired), `iat` (not in future).

**`KeycloakUserCache` model:**

```python
class KeycloakUserCache(Base, table=True):
    __tablename__ = "keycloak_user_cache"

    id: uuid.UUID = Field(default_factory=uuid4, primary_key=True)
    keycloak_sub: str = Field(unique=True, index=True)
    email: str
    full_name: str | None = None
    last_login_at: datetime | None = None
```

Purpose:
- Provides a stable UUID for audit trails and foreign keys from other modules (they reference `keycloak_user_cache.id`, not Keycloak's `sub` string).
- Caches user metadata so the Inertia shared props and menu system have a name/email without calling Keycloak's userinfo endpoint.
- Upserted on each web login callback and on first bearer-token request from a new user.

**Logout (RP-initiated):**

`POST /keycloak/logout` clears the framework session, then redirects to Keycloak's logout endpoint:
`{server_url}/realms/{realm}/protocol/openid-connect/logout?post_logout_redirect_uri={base_url}/keycloak/login&id_token_hint={id_token_from_session}`

### 5. Conflict Detection

**SM020 — Multiple auth providers.** New diagnostic in `ModuleDiagnostics`:

```python
def _check_auth_provider_conflict(self, modules: list[ModuleBase]) -> list[Diagnostic]:
    providers = [m for m in modules if getattr(m, "_is_auth_provider", False)]
    if len(providers) > 1:
        names = ", ".join(m.meta.name for m in providers)
        return [
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SM020",
                message=f"Multiple auth provider modules installed: {names}",
                suggestion="Install only one auth provider (e.g. 'users' OR 'keycloak', not both)",
            )
        ]
    return []
```

**SM021 — No auth provider.** Warns (not errors) if no auth provider is installed — allows headless/API-only deployments that handle auth externally.

```python
if len(providers) == 0:
    return [
        Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM021",
            message="No auth provider module installed",
            suggestion="Install an auth provider module (e.g. 'simple-module-users' or 'simple-module-keycloak')",
        )
    ]
```

The marker `_is_auth_provider = True` is a class attribute on both `UsersModule` and `KeycloakModule`. In production (`strict=True`), SM020 (error) fails boot; SM021 (warning) logs only.

### 6. Shared Infrastructure Moved to `auth/`

These pieces currently live in `users/` but are provider-agnostic:

| What | From | To | Reason |
|------|------|----|--------|
| `AuthMiddleware` | `users/middleware.py` | `auth/middleware.py` | Provider-agnostic; delegates to `AuthProvider` |
| `principal_serializer` | `users/module.py` | `auth/module.py` (`AuthModule.register_settings`) | Serializes `UserContext` for Inertia shared props; provider-agnostic since it only reads `UserContext` fields. Registered on `app.state.principal_serializer` where `InertiaLayoutDataMiddleware` reads it. |
| Framework public paths | `users/middleware.py` | `auth/middleware.py` | `/health`, `/static/`, `/api/docs` are framework-level |

Provider-specific public paths (e.g., `/users/login`, `/keycloak/login`) are returned by each provider's `get_public_paths()`.

`auth/deps.py` (`get_current_user`, `CurrentUser`, `require_permission`) stays unchanged — it reads from `request.state.user` which the middleware sets.

`AuthModule.register_middleware()` now registers the `AuthMiddleware` instead of `UsersModule.register_middleware()`. Since `Users` depends on `Auth`, the middleware ordering is preserved (Auth middleware wraps Users routes).

## Menu Integration

Both providers register appropriate menu items:

**Users module (unchanged):** Users admin, Profile, Logout in the user dropdown.

**Keycloak module:**
- Logout menu item (`POST /keycloak/logout`, user dropdown, order 999).
- Optional: link to Keycloak account console (`{server_url}/realms/{realm}/account`, user dropdown, order 980) — configurable, off by default.
- No "Users admin" menu — user management happens in Keycloak's admin console.
- Role mapping admin page (sidebar, admin-only, order 100) — configure which Keycloak roles map to which framework permission groups.

## Role Mapping

Both providers feed roles into the same `PermissionRegistry`:

**Users module (unchanged):** `User.roles` → `[r.name for r in user.roles]` → `UserContext.roles`.

**Keycloak module:** JWT `realm_access.roles` → filtered through `role_mapping` dict → `UserContext.roles`.

Default mapping (DB-backed, editable via admin UI):

```python
role_mapping: dict[str, str] = {
    "admin": "admin",
    "user": "user",
}
```

Unknown Keycloak roles are silently ignored. The admin UI page lets operators add custom mappings (e.g., Keycloak `editor` → framework `editor` if the app defines that role).

## Module Selection

Framework users choose at install time in their app's `pyproject.toml`:

```toml
# Pick one auth provider:
dependencies = [
    "simple-module-auth",     # always required (contracts layer)
    "simple-module-users",    # local auth — OR:
    # "simple-module-keycloak",  # Keycloak auth
]
```

Both declare the same entry-point group (`simple_module`), both implement `AuthProvider`, and the SM020 diagnostic ensures only one is active.

## Migration Path

For framework users switching from `users` to `keycloak`:

1. Provision Keycloak realm + client (operator responsibility, out of scope).
2. Create matching users in Keycloak (manual or bulk import, out of scope).
3. Replace `simple-module-users` with `simple-module-keycloak` in `pyproject.toml`.
4. Set `SM_KEYCLOAK_*` env vars (or configure via settings UI after first boot with a superuser session cookie).
5. Run `uv sync --all-packages && make migrate` to apply keycloak module's migration.
6. Optionally clean up users module tables: `alembic downgrade users@base`.

No automated data migration — user identity lives in Keycloak.

## Testing Strategy

**Unit tests (keycloak module):**
- `KeycloakAuthProvider.resolve_user()` with mocked JWKS validation.
- JWT validation: valid token, expired, wrong issuer, wrong audience, malformed, key rotation (cache refresh).
- Role mapping: known roles, unknown roles, empty roles, admin bypass.
- OIDC flow: state generation, state validation, code exchange (mocked HTTP).
- `KeycloakUserCache` upsert logic.

**Unit tests (auth middleware):**
- `AuthMiddleware` with a mock `AuthProvider` — verify redirect vs. 401 behavior.
- Bearer token request through the full middleware stack.
- Public path matching (framework-level + provider-specific).
- Principal-resolver chain fallthrough after provider returns None.

**Unit tests (users module changes):**
- `UsersAuthProvider.resolve_user()` — bearer path and session path.
- Refresh token creation, rotation, revocation.
- `POST /api/users/auth/token` returns JSON tokens.
- `POST /api/users/auth/token/refresh` rotates tokens.
- OAuth callback with `Accept: application/json` returns JSON.

**Integration tests:**
- `SM020` / `SM021` diagnostics with various module combinations.
- Full request flow: login → authenticated request → logout, with each provider.
- Bearer token flow: obtain token → API request → token expiry → refresh (users provider only).

**E2E tests (require running Keycloak via Docker):**
- Web login redirect flow with a test Keycloak instance.
- Post-login redirect to `session["next"]`.
- Logout clears both framework session and Keycloak session.
- Role mapping reflected in menu visibility and permission checks.

## Dependencies

**New Python packages (keycloak module only):**
- `PyJWT` — JWT decoding and validation. Already a transitive dep via fastapi-users; used directly for Keycloak JWT validation with RS256.
- `cryptography` — RSA key handling for JWKS. Already a transitive dep.
- `httpx` — async HTTP for OIDC discovery, token exchange, JWKS fetching. Already a project dep.

No new frontend dependencies. No new deps for the `auth` or `users` module changes.

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| JWKS cache staleness (Keycloak rotates signing keys) | Cache TTL + retry: on validation failure with cached keys, refetch JWKS once before rejecting |
| Keycloak downtime blocks all logins | Health check: keycloak module registers a check that probes the OIDC discovery endpoint; alerts fire before users notice |
| `UserContext.id` format mismatch (UUID vs. Keycloak sub) | `KeycloakUserCache` provides a stable UUID; `UserContext.id` always uses the cache table's UUID |
| Other modules FK to `users.User` table | Document that modules should reference `UserContext.id` (UUID string) for audit trails; existing modules that import `users.models.User` directly won't work with keycloak (by design — SM009 already prevents framework→module imports) |
| Session size with Keycloak tokens | Only `UserContext` dict + `id_token` (for logout hint) stored in session; access/refresh tokens are not stored server-side |
| Breaking change: `AuthMiddleware` moves from `users` to `auth` | The middleware was internal to the users module; no other module imports it directly. The observable behavior (request.state.user set, redirects, 401s) is identical. |

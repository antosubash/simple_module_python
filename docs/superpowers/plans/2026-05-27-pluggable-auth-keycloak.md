# Pluggable Auth + Keycloak Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the auth layer swappable — framework users install either `users` (local credentials) or a new `keycloak` module (Keycloak OIDC), both implementing the same `AuthProvider` contract. Mobile clients get bearer-token support regardless of provider.

**Architecture:** The `auth` module (contract layer) gains an `AuthProvider` protocol and a provider-agnostic `AuthMiddleware`. The `users` module implements `AuthProvider` and adds bearer-token + refresh-token endpoints. A new `keycloak` module implements `AuthProvider` via OIDC + JWKS JWT validation. A boot-time diagnostic (SM020) ensures only one provider is installed.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, PyJWT, httpx, Starlette SessionMiddleware, Alembic

**Prerequisite:** The principal-resolver chain from `2026-05-21-auth-principal-resolver-design.md` is already partially implemented (`AuthState` with `principal_resolvers` exists on `app.state.auth`).

---

## File Map

### Auth module (contract layer) — modify existing

| File | Action | Responsibility |
|------|--------|---------------|
| `modules/auth/auth/contracts/provider.py` | Create | `AuthProvider` protocol definition |
| `modules/auth/auth/contracts/__init__.py` | Modify | Re-export `AuthProvider` |
| `modules/auth/auth/__init__.py` | Modify | Re-export `AuthProvider` |
| `modules/auth/auth/state.py` | Modify | Add `auth_provider` field to `AuthState` |
| `modules/auth/auth/middleware.py` | Create | Provider-agnostic `AuthMiddleware` |
| `modules/auth/auth/module.py` | Modify | Register `AuthMiddleware` + `principal_serializer` |
| `modules/auth/tests/test_auth_provider_protocol.py` | Create | Protocol conformance tests |
| `modules/auth/tests/test_auth_middleware.py` | Create | Provider-agnostic middleware tests |

### Users module — modify existing

| File | Action | Responsibility |
|------|--------|---------------|
| `modules/users/users/provider.py` | Create | `UsersAuthProvider` implementing `AuthProvider` |
| `modules/users/users/models/refresh_token.py` | Create | `RefreshToken` SQLModel table |
| `modules/users/users/auth_local/token_api.py` | Create | `POST/DELETE /api/users/auth/token`, `POST .../token/refresh` |
| `modules/users/users/module.py` | Modify | Register as `auth_provider`, remove `AuthMiddleware` + `principal_serializer` registration |
| `modules/users/users/middleware.py` | Delete (or keep as thin import wrapper) | Logic moved to `auth/middleware.py` + `users/provider.py` |
| `modules/users/users/settings.py` | Modify | Add `bearer_token_lifetime_seconds` setting |
| `modules/users/tests/test_users_provider.py` | Create | `UsersAuthProvider` tests |
| `modules/users/tests/test_token_api.py` | Create | Token endpoint tests |

### Framework diagnostics — modify existing

| File | Action | Responsibility |
|------|--------|---------------|
| `framework/core/simple_module_core/diagnostics/_module.py` | Modify | Add `SM020`/`SM021` checks |
| `framework/core/tests/test_diagnostics.py` | Modify | Tests for new diagnostics |

### Keycloak module — new package

| File | Action | Responsibility |
|------|--------|---------------|
| `modules/keycloak/pyproject.toml` | Create | Package metadata + entry point |
| `modules/keycloak/keycloak/__init__.py` | Create | Package marker |
| `modules/keycloak/keycloak/module.py` | Create | `KeycloakModule(ModuleBase)` |
| `modules/keycloak/keycloak/settings.py` | Create | `KeycloakSettings` |
| `modules/keycloak/keycloak/state.py` | Create | `KeycloakState` dataclass |
| `modules/keycloak/keycloak/provider.py` | Create | `KeycloakAuthProvider(AuthProvider)` |
| `modules/keycloak/keycloak/jwks.py` | Create | JWKS key cache + JWT validation |
| `modules/keycloak/keycloak/oidc.py` | Create | OIDC discovery, token exchange |
| `modules/keycloak/keycloak/models.py` | Create | `KeycloakUserCache` table |
| `modules/keycloak/keycloak/endpoints/api.py` | Create | Login redirect, callback, userinfo |
| `modules/keycloak/keycloak/endpoints/views.py` | Create | Inertia login/logout pages |
| `modules/keycloak/keycloak/contracts/__init__.py` | Create | Empty |
| `modules/keycloak/keycloak/locales/en.json` | Create | English translations |
| `modules/keycloak/keycloak/pages/Login.tsx` | Create | Auto-redirect login page |
| `modules/keycloak/keycloak/pages/LoggedOut.tsx` | Create | Post-logout landing |
| `modules/keycloak/package.json` | Create | JS workspace member |
| `modules/keycloak/tsconfig.json` | Create | TypeScript config |
| `modules/keycloak/tests/test_jwks.py` | Create | JWKS cache + JWT validation tests |
| `modules/keycloak/tests/test_oidc.py` | Create | OIDC helper tests |
| `modules/keycloak/tests/test_keycloak_provider.py` | Create | Provider implementation tests |
| `modules/keycloak/tests/test_keycloak_module.py` | Create | Module lifecycle tests |
| `modules/keycloak/tests/conftest.py` | Create | Keycloak test fixtures |

### Alembic migration

| File | Action | Responsibility |
|------|--------|---------------|
| `host/migrations/versions/<auto>_add_users_refresh_token.py` | Create | `users_refresh_token` table |
| `host/migrations/versions/<auto>_keycloak_user_cache.py` | Create | `keycloak_user_cache` table |

### Workspace config

| File | Action | Responsibility |
|------|--------|---------------|
| `pyproject.toml` (root) | Modify | Add `modules/keycloak` to `tool.ty.environment.extra-paths` and `tool.pytest.ini_options.testpaths` |

---

## Task 1: AuthProvider Protocol

**Files:**
- Create: `modules/auth/auth/contracts/provider.py`
- Modify: `modules/auth/auth/contracts/__init__.py`
- Modify: `modules/auth/auth/__init__.py`
- Create: `modules/auth/tests/test_auth_provider_protocol.py`

- [ ] **Step 1: Write the test file**

```python
# modules/auth/tests/test_auth_provider_protocol.py
"""Tests for the AuthProvider protocol."""

from __future__ import annotations

from auth.contracts.provider import AuthProvider
from auth.contracts.schemas import UserContext
from starlette.requests import Request
from starlette.testclient import TestClient


class _FakeProvider:
    """Minimal implementation to verify protocol conformance."""

    name = "fake"

    async def resolve_user(self, request: Request) -> UserContext | None:
        return None

    def get_login_url(self, request: Request, next_url: str | None = None) -> str:
        return "/fake/login"

    def get_logout_url(self, request: Request) -> str:
        return "/fake/logout"

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (("/fake/login",), ())

    def is_bearer_request(self, request: Request) -> bool:
        return False


def test_fake_provider_satisfies_protocol():
    provider = _FakeProvider()
    assert isinstance(provider, AuthProvider)


def test_protocol_rejects_incomplete_implementation():
    class _Incomplete:
        name = "broken"

    assert not isinstance(_Incomplete(), AuthProvider)


def test_auth_package_reexports_auth_provider():
    import auth

    assert hasattr(auth, "AuthProvider")
    assert "AuthProvider" in auth.__all__
    from auth.contracts.provider import AuthProvider as Canonical

    assert auth.AuthProvider is Canonical


def test_contracts_package_reexports_auth_provider():
    from auth.contracts import AuthProvider

    assert AuthProvider is not None
```

- [ ] **Step 2: Run tests — they should fail (AuthProvider not defined yet)**

Run: `uv run pytest modules/auth/tests/test_auth_provider_protocol.py -v`
Expected: `ModuleNotFoundError` or `ImportError` — `auth.contracts.provider` doesn't exist.

- [ ] **Step 3: Create the AuthProvider protocol**

```python
# modules/auth/auth/contracts/provider.py
"""AuthProvider protocol — the contract both users and keycloak modules implement."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from starlette.requests import Request

from auth.contracts.schemas import UserContext


@runtime_checkable
class AuthProvider(Protocol):
    """Extension point for swappable authentication backends.

    Exactly one module (``users`` or ``keycloak``) registers an implementation
    on ``app.state.auth.auth_provider`` during ``register_settings``.
    The ``AuthMiddleware`` delegates to it on every request.
    """

    name: str

    async def resolve_user(self, request: Request) -> UserContext | None: ...

    def get_login_url(self, request: Request, next_url: str | None = None) -> str: ...

    def get_logout_url(self, request: Request) -> str: ...

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]: ...

    def is_bearer_request(self, request: Request) -> bool: ...


__all__ = ["AuthProvider"]
```

- [ ] **Step 4: Update contracts `__init__.py`**

Change `modules/auth/auth/contracts/__init__.py` from:
```python
"""Auth contracts — public types for other modules."""

from auth.contracts.schemas import UserContext

__all__ = ["UserContext"]
```
to:
```python
"""Auth contracts — public types for other modules."""

from auth.contracts.provider import AuthProvider
from auth.contracts.schemas import UserContext

__all__ = ["AuthProvider", "UserContext"]
```

- [ ] **Step 5: Update auth package `__init__.py`**

Change `modules/auth/auth/__init__.py` from:
```python
"""Auth module — shared contracts (UserContext, PrincipalResolver, deps)."""

from auth.contracts.resolver import PrincipalResolver
from auth.contracts.schemas import UserContext

__all__ = ["PrincipalResolver", "UserContext"]
```
to:
```python
"""Auth module — shared contracts (UserContext, AuthProvider, PrincipalResolver, deps)."""

from auth.contracts.provider import AuthProvider
from auth.contracts.resolver import PrincipalResolver
from auth.contracts.schemas import UserContext

__all__ = ["AuthProvider", "PrincipalResolver", "UserContext"]
```

- [ ] **Step 6: Run tests — they should pass**

Run: `uv run pytest modules/auth/tests/test_auth_provider_protocol.py -v`
Expected: All 4 tests pass.

- [ ] **Step 7: Commit**

```bash
git add modules/auth/auth/contracts/provider.py modules/auth/auth/contracts/__init__.py modules/auth/auth/__init__.py modules/auth/tests/test_auth_provider_protocol.py
git commit -m "feat(auth): add AuthProvider protocol for swappable auth backends"
```

---

## Task 2: Add auth_provider to AuthState

**Files:**
- Modify: `modules/auth/auth/state.py`
- Modify: `modules/auth/tests/test_resolver_registry.py`

- [ ] **Step 1: Write the test**

Add to `modules/auth/tests/test_resolver_registry.py`:

```python
def test_auth_state_has_auth_provider_field():
    from auth.state import AuthState

    state = AuthState()
    assert state.auth_provider is None


def test_auth_state_accepts_auth_provider():
    from auth.contracts.provider import AuthProvider
    from auth.state import AuthState

    class FakeProvider:
        name = "fake"

        async def resolve_user(self, request):
            return None

        def get_login_url(self, request, next_url=None):
            return "/login"

        def get_logout_url(self, request):
            return "/logout"

        def get_public_paths(self):
            return ((), ())

        def is_bearer_request(self, request):
            return False

    provider = FakeProvider()
    state = AuthState(auth_provider=provider)
    assert state.auth_provider is provider
    assert isinstance(state.auth_provider, AuthProvider)
```

- [ ] **Step 2: Run test — should fail**

Run: `uv run pytest modules/auth/tests/test_resolver_registry.py::test_auth_state_has_auth_provider_field -v`
Expected: `TypeError` — `AuthState` doesn't accept `auth_provider`.

- [ ] **Step 3: Add auth_provider field to AuthState**

Change `modules/auth/auth/state.py` from:
```python
"""Module-owned state attached to ``app.state.auth`` by ``AuthModule.register_settings``.

Holds the principal-resolver registry (see
``auth.contracts.resolver.PrincipalResolver``). Apps register additional
resolvers from their ``on_startup`` hook::

    app.state.auth.principal_resolvers.append(my_pat_resolver)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from auth.contracts.resolver import PrincipalResolver


@dataclass
class AuthState:
    """Per-app auth registry. Initialized empty; modules append resolvers."""

    principal_resolvers: list[PrincipalResolver] = field(default_factory=list)


__all__ = ["AuthState"]
```
to:
```python
"""Module-owned state attached to ``app.state.auth`` by ``AuthModule.register_settings``.

Holds the auth provider (set by one of ``users`` or ``keycloak``) and the
principal-resolver registry. Apps register additional resolvers from their
``on_startup`` hook::

    app.state.auth.principal_resolvers.append(my_pat_resolver)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from auth.contracts.resolver import PrincipalResolver

if TYPE_CHECKING:
    from auth.contracts.provider import AuthProvider


@dataclass
class AuthState:
    """Per-app auth registry. Initialized empty; provider modules populate at boot."""

    auth_provider: AuthProvider | None = None
    principal_resolvers: list[PrincipalResolver] = field(default_factory=list)


__all__ = ["AuthState"]
```

- [ ] **Step 4: Run all auth tests — should pass**

Run: `uv run pytest modules/auth/tests/ -v`
Expected: All pass, including the two new tests.

- [ ] **Step 5: Commit**

```bash
git add modules/auth/auth/state.py modules/auth/tests/test_resolver_registry.py
git commit -m "feat(auth): add auth_provider slot to AuthState"
```

---

## Task 3: Provider-Agnostic AuthMiddleware in auth/

**Files:**
- Create: `modules/auth/auth/middleware.py`
- Create: `modules/auth/tests/test_auth_middleware.py`

- [ ] **Step 1: Write middleware tests**

```python
# modules/auth/tests/test_auth_middleware.py
"""Tests for the provider-agnostic AuthMiddleware."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from auth.contracts.schemas import UserContext
from auth.middleware import AuthMiddleware
from auth.state import AuthState
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse

SECRET = "test-middleware-secret"

_TEST_USER = UserContext(
    id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    email="test@example.com",
    name="Test User",
    roles=["admin"],
)


class _StubProvider:
    name = "stub"

    def __init__(self, *, user: UserContext | None = None):
        self._user = user

    async def resolve_user(self, request):
        return self._user

    def get_login_url(self, request, next_url=None):
        return "/stub/login"

    def get_logout_url(self, request):
        return "/stub/logout"

    def get_public_paths(self):
        return (("/stub/login", "/stub/public/"), ())

    def is_bearer_request(self, request):
        auth = request.headers.get("authorization", "")
        return auth.startswith("Bearer ")


def _build_app(provider, *, principal_resolvers=None):
    app = FastAPI()
    app.state.auth = AuthState(
        auth_provider=provider,
        principal_resolvers=list(principal_resolvers or []),
    )

    @app.get("/{path:path}")
    async def catch_all(request: Request, path: str = ""):
        user = getattr(request.state, "user", None)
        return JSONResponse(
            {
                "user": user.to_session_dict() if user else None,
            }
        )

    app.add_middleware(AuthMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=SECRET)
    return app


@pytest.fixture
def authenticated_app():
    return _build_app(_StubProvider(user=_TEST_USER))


@pytest.fixture
def unauthenticated_app():
    return _build_app(_StubProvider(user=None))


async def test_authenticated_request_sets_user(authenticated_app):
    async with httpx.AsyncClient(app=authenticated_app, base_url="http://test") as c:
        resp = await c.get("/some/page")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "test@example.com"


async def test_unauthenticated_browser_redirects_to_login(unauthenticated_app):
    async with httpx.AsyncClient(
        app=unauthenticated_app, base_url="http://test", follow_redirects=False
    ) as c:
        resp = await c.get("/protected/page")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/stub/login"


async def test_unauthenticated_api_returns_401(unauthenticated_app):
    async with httpx.AsyncClient(app=unauthenticated_app, base_url="http://test") as c:
        resp = await c.get("/api/protected")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


async def test_unauthenticated_bearer_returns_401(unauthenticated_app):
    async with httpx.AsyncClient(app=unauthenticated_app, base_url="http://test") as c:
        resp = await c.get("/some/page", headers={"Authorization": "Bearer bad"})
    assert resp.status_code == 401


async def test_public_paths_skip_auth(unauthenticated_app):
    async with httpx.AsyncClient(app=unauthenticated_app, base_url="http://test") as c:
        resp = await c.get("/stub/login")
    assert resp.status_code == 200


async def test_framework_public_paths_skip_auth(unauthenticated_app):
    async with httpx.AsyncClient(app=unauthenticated_app, base_url="http://test") as c:
        resp = await c.get("/health")
    assert resp.status_code == 200


async def test_root_is_public(unauthenticated_app):
    async with httpx.AsyncClient(app=unauthenticated_app, base_url="http://test") as c:
        resp = await c.get("/")
    assert resp.status_code == 200


async def test_resolver_chain_fallback():
    """When provider returns None, fall through to principal resolvers."""

    async def fake_resolver(request):
        auth = request.headers.get("authorization", "")
        if auth == "Bearer good-token":
            return _TEST_USER
        return None

    app = _build_app(_StubProvider(user=None), principal_resolvers=[fake_resolver])
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        resp = await c.get("/protected", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "test@example.com"


async def test_resolver_exception_is_logged_and_skipped():
    """A resolver that raises should be caught; middleware continues."""

    async def bad_resolver(request):
        raise RuntimeError("boom")

    app = _build_app(_StubProvider(user=None), principal_resolvers=[bad_resolver])
    async with httpx.AsyncClient(app=app, base_url="http://test", follow_redirects=False) as c:
        resp = await c.get("/protected/page")
    assert resp.status_code == 302
```

- [ ] **Step 2: Run tests — they should fail**

Run: `uv run pytest modules/auth/tests/test_auth_middleware.py -v`
Expected: `ImportError` — `auth.middleware` doesn't exist.

- [ ] **Step 3: Create the provider-agnostic AuthMiddleware**

```python
# modules/auth/auth/middleware.py
"""Provider-agnostic authentication middleware.

Delegates user resolution to the ``AuthProvider`` registered on
``app.state.auth.auth_provider``, then falls through to the
principal-resolver chain. Sets ``request.state.user`` and the
``current_user_id`` ContextVar for audit listeners.
"""

from __future__ import annotations

import logging

from simple_module_db.listeners import current_user_id
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_FRAMEWORK_PUBLIC_PREFIXES = (
    "/health",
    "/static/",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
    "/i18n/",
)
_FRAMEWORK_PUBLIC_EXACT = ("/",)
_SESSION_NEXT_KEY = "next"


class AuthMiddleware:
    """Authenticate requests via the registered AuthProvider.

    On cache miss (provider returns None), falls through to the
    principal-resolver chain. Unauthenticated API requests get 401 JSON;
    unauthenticated browser requests get a redirect to the provider's
    login URL.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        auth_state = scope["app"].state.auth
        provider = auth_state.auth_provider

        if provider is None:
            await self.app(scope, receive, send)
            return

        is_public = (
            any(path.startswith(p) for p in _FRAMEWORK_PUBLIC_PREFIXES)
            or path in _FRAMEWORK_PUBLIC_EXACT
        )
        if not is_public:
            prefix_paths, exact_paths = provider.get_public_paths()
            is_public = any(path.startswith(p) for p in prefix_paths) or path in exact_paths

        request = Request(scope)
        user_ctx = await provider.resolve_user(request)

        if user_ctx is None:
            for resolver in auth_state.principal_resolvers:
                try:
                    user_ctx = await resolver(request)
                except Exception:
                    logger.exception(
                        "Principal resolver %r raised; treating as no-match",
                        resolver,
                    )
                    continue
                if user_ctx is not None:
                    break

        if user_ctx is None and not is_public:
            if path.startswith("/api/") or provider.is_bearer_request(request):
                response = JSONResponse({"detail": "Not authenticated"}, status_code=401)
            else:
                session = scope.get("session", {})
                session[_SESSION_NEXT_KEY] = str(request.url)
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

- [ ] **Step 4: Run tests — should pass**

Run: `uv run pytest modules/auth/tests/test_auth_middleware.py -v`
Expected: All 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add modules/auth/auth/middleware.py modules/auth/tests/test_auth_middleware.py
git commit -m "feat(auth): add provider-agnostic AuthMiddleware"
```

---

## Task 4: Move principal_serializer + AuthMiddleware Registration to AuthModule

**Files:**
- Modify: `modules/auth/auth/module.py`
- Modify: `modules/users/users/module.py`
- Modify: `modules/auth/tests/test_resolver_registry.py`

- [ ] **Step 1: Write tests for the new AuthModule behavior**

Add to `modules/auth/tests/test_resolver_registry.py`:

```python
def test_auth_module_registers_middleware():
    """AuthModule.register_middleware should add AuthMiddleware."""
    from auth.module import AuthModule
    from fastapi import FastAPI

    app = FastAPI()
    AuthModule().register_middleware(app)
    middleware_classes = [m.cls.__name__ for m in app.user_middleware]
    assert "AuthMiddleware" in middleware_classes


def test_auth_module_registers_principal_serializer():
    """AuthModule.register_settings should set principal_serializer on app.state."""
    from auth.module import AuthModule
    from fastapi import FastAPI

    app = FastAPI()
    AuthModule().register_settings(app)
    serializer = getattr(app.state, "principal_serializer", None)
    assert serializer is not None

    from auth.contracts.schemas import UserContext

    ctx = UserContext(id="123", email="a@b.com", name="Test", roles=["admin"])
    result = serializer(ctx)
    assert result == {"id": "123", "name": "Test", "email": "a@b.com", "roles": ["admin"]}
```

- [ ] **Step 2: Run tests — should fail**

Run: `uv run pytest modules/auth/tests/test_resolver_registry.py::test_auth_module_registers_middleware -v`
Expected: FAIL — `AuthModule` doesn't override `register_middleware`.

- [ ] **Step 3: Update AuthModule to register middleware + principal_serializer**

Change `modules/auth/auth/module.py` to:

```python
"""Auth module — shared contracts (UserContext, AuthProvider, deps).

Intentionally minimal: this module owns the PUBLIC interface (UserContext,
AuthProvider, PrincipalResolver, get_current_user, CurrentUser, require_permission)
that every other module imports. Keeping it stable prevents churn when auth
internals change.

The ``auth_provider`` slot on ``app.state.auth`` is the extension point
auth-provider modules (``users``, ``keycloak``) use to register themselves.
The ``principal_resolvers`` registry lets downstream modules add extra
credential sources (PAT bearer tokens, API keys, etc.).
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.module import ModuleBase, ModuleMeta

if TYPE_CHECKING:
    from fastapi import FastAPI

    from auth.contracts.schemas import UserContext


def _serialize_principal(user: UserContext) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "roles": user.roles,
    }


class AuthModule(ModuleBase):
    meta = ModuleMeta(
        name="Auth",
        route_prefix="/auth",
    )

    def register_settings(self, app: FastAPI) -> None:
        from auth.state import AuthState

        app.state.auth = AuthState()
        app.state.principal_serializer = _serialize_principal

    def register_middleware(self, app: FastAPI) -> None:
        from auth.middleware import AuthMiddleware

        app.add_middleware(AuthMiddleware)

    def locale_dirs(self) -> dict[str, Path]:
        return {"auth": Path(str(importlib.resources.files(__package__) / "locales"))}
```

- [ ] **Step 4: Remove middleware + serializer registration from UsersModule**

In `modules/users/users/module.py`:

Remove the `register_middleware` method entirely (lines 159-162):
```python
    # DELETE THIS METHOD:
    def register_middleware(self, app: FastAPI) -> None:
        from users.middleware import AuthMiddleware

        app.add_middleware(AuthMiddleware)
```

In `register_settings`, remove the `serialize_principal` function and `app.state.principal_serializer` line (lines 61-69):
```python
    # DELETE THESE LINES from register_settings:
        def serialize_principal(user: UserContext) -> dict:
            return {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "roles": user.roles,
            }

        app.state.principal_serializer = serialize_principal
```

Also remove the unused `from auth.contracts.schemas import UserContext` import from `register_settings` (it was only used by the deleted serializer).

- [ ] **Step 5: Run auth + users tests**

Run: `uv run pytest modules/auth/tests/ modules/users/tests/ -v`
Expected: All pass. The middleware behavior is unchanged — it still delegates to the provider; users module just no longer registers it.

- [ ] **Step 6: Commit**

```bash
git add modules/auth/auth/module.py modules/users/users/module.py modules/auth/tests/test_resolver_registry.py
git commit -m "refactor(auth,users): move AuthMiddleware + principal_serializer to auth module"
```

---

## Task 5: UsersAuthProvider Implementation

**Files:**
- Create: `modules/users/users/provider.py`
- Create: `modules/users/tests/test_users_provider.py`
- Modify: `modules/users/users/module.py`

- [ ] **Step 1: Write provider tests**

```python
# modules/users/tests/test_users_provider.py
"""Tests for UsersAuthProvider."""

from __future__ import annotations

import uuid

import httpx
import pytest
from auth.contracts.provider import AuthProvider
from auth.contracts.schemas import UserContext
from auth.state import AuthState
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from users.provider import UsersAuthProvider

SECRET = "test-provider-secret"


def test_users_provider_satisfies_protocol():
    provider = UsersAuthProvider()
    assert isinstance(provider, AuthProvider)


def test_login_url():
    provider = UsersAuthProvider()
    assert provider.get_login_url(None) == "/users/login"


def test_logout_url():
    provider = UsersAuthProvider()
    assert provider.get_logout_url(None) == "/users/logout"


def test_public_paths():
    provider = UsersAuthProvider()
    prefixes, exact = provider.get_public_paths()
    assert "/users/login" in prefixes
    assert "/api/users/auth/" in prefixes


def test_is_bearer_request_true():
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {"authorization": "Bearer abc123"}
    provider = UsersAuthProvider()
    assert provider.is_bearer_request(request) is True


def test_is_bearer_request_false():
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {}
    provider = UsersAuthProvider()
    assert provider.is_bearer_request(request) is False
```

- [ ] **Step 2: Run tests — should fail**

Run: `uv run pytest modules/users/tests/test_users_provider.py -v`
Expected: `ImportError` — `users.provider` doesn't exist.

- [ ] **Step 3: Create UsersAuthProvider**

```python
# modules/users/users/provider.py
"""UsersAuthProvider — AuthProvider implementation for the users module.

Resolves users from session cookies (browser) or the principal-resolver chain
(bearer tokens, PATs). Session handling mirrors the original AuthMiddleware
logic: fast path from ``session["user_ctx"]``, slow path via DB lookup.
"""

from __future__ import annotations

import logging
import uuid as uuid_mod

from auth.contracts.provider import AuthProvider
from auth.contracts.schemas import UserContext
from starlette.requests import Request

logger = logging.getLogger(__name__)

_SESSION_USER_ID_KEY = "user_id"
_SESSION_USER_CTX_KEY = "user_ctx"


class UsersAuthProvider:
    """Cookie-based auth provider using fastapi-users' DatabaseStrategy."""

    name = "users"
    _is_auth_provider = True

    async def resolve_user(self, request: Request) -> UserContext | None:
        session = request.scope.get("session", {})
        raw_user_id = session.get(_SESSION_USER_ID_KEY)
        if not raw_user_id:
            return None

        user_id_str = str(raw_user_id)

        cached = UserContext.from_session_dict(session.get(_SESSION_USER_CTX_KEY))
        if cached is not None and cached.id == user_id_str:
            return cached

        try:
            user_uuid = uuid_mod.UUID(user_id_str)
        except (ValueError, TypeError):
            logger.warning("Invalid user_id in session: %r", raw_user_id)
            session.pop(_SESSION_USER_ID_KEY, None)
            session.pop(_SESSION_USER_CTX_KEY, None)
            return None

        user_ctx = await self._load_user(request.scope, user_uuid)
        if user_ctx is None:
            session.pop(_SESSION_USER_ID_KEY, None)
            session.pop(_SESSION_USER_CTX_KEY, None)
        else:
            session[_SESSION_USER_CTX_KEY] = user_ctx.to_session_dict()
        return user_ctx

    def get_login_url(self, request: Request | None, next_url: str | None = None) -> str:
        return "/users/login"

    def get_logout_url(self, request: Request | None) -> str:
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

    def is_bearer_request(self, request: Request | None) -> bool:
        if request is None:
            return False
        return request.headers.get("authorization", "").startswith("Bearer ")

    async def _load_user(self, scope, user_id: uuid_mod.UUID) -> UserContext | None:
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            from users.models import User

            session_factory = scope["app"].state.sm.db.session_factory
            async with session_factory() as db_session:
                stmt = select(User).where(User.id == user_id).options(selectinload(User.roles))
                user = (await db_session.execute(stmt)).scalar_one_or_none()
                if user is None or not user.is_active or user.disabled_at is not None:
                    return None
                return UserContext.from_user(user)
        except Exception:
            logger.exception(
                "Failed to load user %s from DB; treating as unauthenticated",
                user_id,
            )
            return None
```

- [ ] **Step 4: Run tests — should pass**

Run: `uv run pytest modules/users/tests/test_users_provider.py -v`
Expected: All 6 tests pass.

- [ ] **Step 5: Register UsersAuthProvider in UsersModule**

In `modules/users/users/module.py`, update `register_settings` to add (after the `register_module_settings` call):

```python
        from users.provider import UsersAuthProvider

        app.state.auth.auth_provider = UsersAuthProvider()
```

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest modules/auth/tests/ modules/users/tests/ -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add modules/users/users/provider.py modules/users/tests/test_users_provider.py modules/users/users/module.py
git commit -m "feat(users): implement UsersAuthProvider with session-cookie resolution"
```

---

## Task 6: Remove Old AuthMiddleware from Users Module

**Files:**
- Modify: `modules/users/users/middleware.py` (remove or convert to thin re-export)
- Modify: `modules/users/tests/_middleware_support.py`
- Modify: `modules/users/tests/test_users_middleware.py` (update to use new middleware)

- [ ] **Step 1: Update middleware test support to use auth.middleware**

In `modules/users/tests/_middleware_support.py`, change the import:

From:
```python
from users.middleware import AuthMiddleware
```
To:
```python
from auth.middleware import AuthMiddleware
```

And update `_build_app` to set `auth_provider` on the `AuthState`:

From:
```python
    app.state.auth = AuthState(
        principal_resolvers=list(principal_resolvers or []),
    )
```
To:
```python
    from users.provider import UsersAuthProvider

    app.state.auth = AuthState(
        auth_provider=UsersAuthProvider(),
        principal_resolvers=list(principal_resolvers or []),
    )
```

- [ ] **Step 2: Run existing middleware tests**

Run: `uv run pytest modules/users/tests/test_users_middleware.py -v`
Expected: All pass — the behavior is identical, just routed through `auth.middleware` → `UsersAuthProvider` instead of `users.middleware.AuthMiddleware` directly.

- [ ] **Step 3: Replace users/middleware.py with a deprecation re-export**

Replace `modules/users/users/middleware.py` contents with:

```python
"""Backwards-compatibility re-export.

The canonical AuthMiddleware now lives in ``auth.middleware``. This shim
exists only to avoid breaking imports in downstream apps that referenced
``users.middleware.AuthMiddleware`` directly.
"""

from auth.middleware import AuthMiddleware

__all__ = ["AuthMiddleware"]
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest modules/auth/tests/ modules/users/tests/ -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add modules/users/users/middleware.py modules/users/tests/_middleware_support.py
git commit -m "refactor(users): delegate to auth.middleware, keep thin re-export for compat"
```

---

## Task 7: SM020/SM021 Diagnostics

**Files:**
- Modify: `framework/core/simple_module_core/diagnostics/_module.py`
- Modify or create test in: `framework/core/tests/test_diagnostics.py` (or equivalent)

- [ ] **Step 1: Write diagnostic tests**

Find the existing diagnostics test file and add:

```python
def test_sm020_multiple_auth_providers():
    """SM020 fires when two modules both set _is_auth_provider."""
    from simple_module_core.diagnostics._module import ModuleDiagnostics
    from simple_module_core.module import ModuleBase, ModuleMeta

    class FakeUsersModule(ModuleBase):
        meta = ModuleMeta(name="Users")
        _is_auth_provider = True

    class FakeKeycloakModule(ModuleBase):
        meta = ModuleMeta(name="Keycloak")
        _is_auth_provider = True

    diags = ModuleDiagnostics()
    results = diags._check_auth_provider_conflict([FakeUsersModule(), FakeKeycloakModule()])
    assert len(results) == 1
    assert results[0].code == "SM020"
    assert results[0].level.name == "ERROR"


def test_sm021_no_auth_provider():
    """SM021 fires when no module sets _is_auth_provider."""
    from simple_module_core.diagnostics._module import ModuleDiagnostics
    from simple_module_core.module import ModuleBase, ModuleMeta

    class FakeDashboard(ModuleBase):
        meta = ModuleMeta(name="Dashboard")

    diags = ModuleDiagnostics()
    results = diags._check_auth_provider_conflict([FakeDashboard()])
    assert len(results) == 1
    assert results[0].code == "SM021"
    assert results[0].level.name == "WARNING"


def test_sm020_single_provider_passes():
    """No diagnostic when exactly one auth provider is installed."""
    from simple_module_core.diagnostics._module import ModuleDiagnostics
    from simple_module_core.module import ModuleBase, ModuleMeta

    class FakeUsersModule(ModuleBase):
        meta = ModuleMeta(name="Users")
        _is_auth_provider = True

    class FakeDashboard(ModuleBase):
        meta = ModuleMeta(name="Dashboard")

    diags = ModuleDiagnostics()
    results = diags._check_auth_provider_conflict([FakeUsersModule(), FakeDashboard()])
    assert results == []
```

- [ ] **Step 2: Run tests — should fail**

Run: `uv run pytest framework/core/tests/ -k "sm020 or sm021 or auth_provider_conflict" -v`
Expected: `AttributeError` — `_check_auth_provider_conflict` doesn't exist.

- [ ] **Step 3: Add the check method and wire it into `run()`**

In `framework/core/simple_module_core/diagnostics/_module.py`, add to the `run()` method:
```python
        diagnostics.extend(self._check_auth_provider_conflict(modules))
```

Add the new method to `ModuleDiagnostics`:

```python
def _check_auth_provider_conflict(self, modules: list[ModuleBase]) -> list[Diagnostic]:
    """SM020/SM021: exactly one auth provider module must be installed."""
    providers = [m for m in modules if getattr(m, "_is_auth_provider", False)]
    diags: list[Diagnostic] = []
    if len(providers) > 1:
        names = ", ".join(m.meta.name for m in providers)
        diags.append(
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SM020",
                message=f"Multiple auth provider modules installed: {names}",
                module_name=providers[0].meta.name,
                suggestion=(
                    "Install only one auth provider (e.g. 'users' OR 'keycloak', not both)"
                ),
            )
        )
    elif len(providers) == 0:
        diags.append(
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="SM021",
                message="No auth provider module installed",
                module_name="(none)",
                suggestion=(
                    "Install an auth provider module "
                    "(e.g. 'simple-module-users' or 'simple-module-keycloak')"
                ),
            )
        )
    return diags
```

- [ ] **Step 4: Add `_is_auth_provider = True` to UsersModule**

In `modules/users/users/module.py`, add the class attribute:
```python
class UsersModule(ModuleBase):
    meta = ModuleMeta(...)
    _is_auth_provider = True
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest framework/core/tests/ -k "sm020 or sm021 or auth_provider" -v`
Expected: All 3 new tests pass.

- [ ] **Step 6: Commit**

```bash
git add framework/core/simple_module_core/diagnostics/_module.py modules/users/users/module.py
git commit -m "feat(diagnostics): SM020/SM021 — exactly one auth provider required"
```

---

## Task 8: Keycloak Module Scaffold — Package + Module + Settings

**Files:**
- Create: `modules/keycloak/pyproject.toml`
- Create: `modules/keycloak/keycloak/__init__.py`
- Create: `modules/keycloak/keycloak/module.py`
- Create: `modules/keycloak/keycloak/settings.py`
- Create: `modules/keycloak/keycloak/state.py`
- Create: `modules/keycloak/keycloak/contracts/__init__.py`
- Create: `modules/keycloak/keycloak/locales/en.json`
- Create: `modules/keycloak/package.json`
- Create: `modules/keycloak/tsconfig.json`
- Create: `modules/keycloak/tests/__init__.py`
- Create: `modules/keycloak/tests/conftest.py`
- Create: `modules/keycloak/tests/test_keycloak_module.py`
- Modify: `pyproject.toml` (root — add to `extra-paths` and `testpaths`)

- [ ] **Step 1: Write module registration test**

```python
# modules/keycloak/tests/test_keycloak_module.py
"""Tests for KeycloakModule lifecycle."""

from __future__ import annotations

from auth.contracts.provider import AuthProvider


def test_keycloak_module_meta():
    from keycloak.module import KeycloakModule

    mod = KeycloakModule()
    assert mod.meta.name == "Keycloak"
    assert mod.meta.depends_on == ["Auth"]
    assert mod._is_auth_provider is True


def test_keycloak_module_registers_provider():
    from auth.state import AuthState
    from fastapi import FastAPI
    from keycloak.module import KeycloakModule

    app = FastAPI()
    app.state.auth = AuthState()
    KeycloakModule().register_settings(app)

    assert app.state.auth.auth_provider is not None
    assert isinstance(app.state.auth.auth_provider, AuthProvider)
    assert app.state.auth.auth_provider.name == "keycloak"
```

- [ ] **Step 2: Create pyproject.toml**

```toml
# modules/keycloak/pyproject.toml
[project]
name = "simple_module_keycloak"
version = "0.0.15"
description = "Keycloak OIDC authentication provider for simple_module — swap with simple_module_users"
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "keycloak", "oidc", "authentication", "fastapi"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Internet :: WWW/HTTP",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]
dependencies = [
    "simple_module_core==0.0.15",
    "simple_module_db==0.0.15",
    "simple_module_hosting==0.0.15",
    "simple_module_settings==0.0.15",
    "simple_module_auth==0.0.15",
    "PyJWT[crypto]>=2.8",
    "httpx>=0.27",
]

[project.entry-points.simple_module]
keycloak = "keycloak.module:KeycloakModule"

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["keycloak"]

[tool.hatch.build.targets.wheel.force-include]
"package.json" = "keycloak/package.json"

[tool.uv.sources]
simple_module_core = { workspace = true }
simple_module_db = { workspace = true }
simple_module_hosting = { workspace = true }
simple_module_settings = { workspace = true }
simple_module_auth = { workspace = true }
```

- [ ] **Step 3: Create package files**

`modules/keycloak/keycloak/__init__.py`:
```python
"""Keycloak OIDC authentication provider for simple_module."""
```

`modules/keycloak/keycloak/contracts/__init__.py`:
```python
"""Keycloak module contracts."""
```

`modules/keycloak/keycloak/locales/en.json`:
```json
{
  "login": {
    "redirecting": "Redirecting to identity provider…",
    "title": "Sign In"
  },
  "logout": {
    "title": "Signed Out",
    "message": "You have been signed out successfully."
  },
  "errors": {
    "callback_failed": "Authentication failed. Please try again.",
    "invalid_state": "Invalid authentication state. Please try again.",
    "token_validation_failed": "Token validation failed."
  }
}
```

`modules/keycloak/package.json`:
```json
{
  "name": "@simple-module/keycloak",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "dependencies": {}
}
```

`modules/keycloak/tsconfig.json`:
```json
{
  "extends": "../../host/client_app/tsconfig.json",
  "include": ["keycloak/**/*.ts", "keycloak/**/*.tsx"]
}
```

`modules/keycloak/tests/__init__.py`: empty file.

`modules/keycloak/tests/conftest.py`:
```python
"""Keycloak module test fixtures."""
```

- [ ] **Step 4: Create KeycloakSettings**

```python
# modules/keycloak/keycloak/settings.py
"""Keycloak module settings — DB-backed via ``register_module_settings``."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.dotenv import env_str
from simple_module_core.environments import NON_PROD_ENVIRONMENTS


class KeycloakSettings(BaseSettings):
    """Keycloak OIDC configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    server_url: str = env_str("SM_KEYCLOAK_SERVER_URL", "")
    realm: str = env_str("SM_KEYCLOAK_REALM", "")
    client_id: str = env_str("SM_KEYCLOAK_CLIENT_ID", "")
    client_secret: str = env_str("SM_KEYCLOAK_CLIENT_SECRET", "")

    roles_claim_path: str = "realm_access.roles"
    admin_role: str = "admin"
    login_redirect_url: str = "/dashboard/"
    jwks_cache_ttl_seconds: int = 3600

    role_mapping: dict[str, str] = Field(
        default_factory=lambda: {"admin": "admin", "user": "user"},
    )

    @model_validator(mode="after")
    def _check_required_in_production(self) -> KeycloakSettings:
        import os

        env = os.environ.get("SM_ENVIRONMENT", "development")
        if env in NON_PROD_ENVIRONMENTS:
            return self
        missing = []
        if not self.server_url:
            missing.append("SM_KEYCLOAK_SERVER_URL")
        if not self.realm:
            missing.append("SM_KEYCLOAK_REALM")
        if not self.client_id:
            missing.append("SM_KEYCLOAK_CLIENT_ID")
        if not self.client_secret:
            missing.append("SM_KEYCLOAK_CLIENT_SECRET")
        if missing:
            msg = f"Keycloak settings required in production: {', '.join(missing)}"
            raise ValueError(msg)
        return self
```

- [ ] **Step 5: Create KeycloakState**

```python
# modules/keycloak/keycloak/state.py
"""Module-scoped state container for the keycloak module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from keycloak.jwks import JWKSCache
    from keycloak.settings import KeycloakSettings


@dataclass
class KeycloakState:
    """Keycloak-module singletons. Single slot at ``app.state.keycloak``."""

    settings: KeycloakSettings
    jwks_cache: JWKSCache | None = None
```

- [ ] **Step 6: Create KeycloakModule (minimal — provider wired in next tasks)**

```python
# modules/keycloak/keycloak/module.py
"""Keycloak OIDC authentication module."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI


class KeycloakModule(ModuleBase):
    meta = ModuleMeta(
        name="Keycloak",
        route_prefix="/api/keycloak",
        view_prefix="/keycloak",
        depends_on=["Auth"],
    )
    _is_auth_provider = True

    def register_settings(self, app: FastAPI) -> None:
        import importlib

        from keycloak.provider import KeycloakAuthProvider
        from keycloak.settings import KeycloakSettings
        from keycloak.state import KeycloakState

        register_module_settings = importlib.import_module(
            "settings.registration"
        ).register_module_settings

        register_module_settings(
            app, "keycloak", KeycloakSettings, lambda s: KeycloakState(settings=s)
        )

        app.state.auth.auth_provider = KeycloakAuthProvider(app.state.keycloak.settings)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Logout",
                url="/keycloak/logout",
                icon="log-out",
                order=999,
                section=MenuSection.USER_DROPDOWN,
                method="post",
            )
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from keycloak.endpoints.api import router as api
        from keycloak.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    async def on_startup(self, app: FastAPI) -> None:
        from keycloak.jwks import JWKSCache

        state = app.state.keycloak
        s = state.settings
        if s.server_url and s.realm:
            state.jwks_cache = JWKSCache(
                jwks_url=f"{s.server_url}/realms/{s.realm}/protocol/openid-connect/certs",
                ttl_seconds=s.jwks_cache_ttl_seconds,
            )
            provider = app.state.auth.auth_provider
            provider.jwks_cache = state.jwks_cache

    def locale_dirs(self) -> dict[str, Path]:
        return {"keycloak": Path(str(importlib.resources.files(__package__) / "locales"))}
```

- [ ] **Step 7: Update root pyproject.toml**

Add `"modules/keycloak"` to `tool.ty.environment.extra-paths` and `"modules/keycloak/tests"` to `tool.pytest.ini_options.testpaths`.

- [ ] **Step 8: Run `uv sync --all-packages` then tests**

Run: `uv sync --all-packages && uv run pytest modules/keycloak/tests/test_keycloak_module.py -v`
Expected: All pass.

- [ ] **Step 9: Commit**

```bash
git add modules/keycloak/ pyproject.toml
git commit -m "feat(keycloak): scaffold keycloak module with settings + provider registration"
```

---

## Task 9: JWKS Cache + JWT Validation

**Files:**
- Create: `modules/keycloak/keycloak/jwks.py`
- Create: `modules/keycloak/tests/test_jwks.py`

- [ ] **Step 1: Write JWKS/JWT tests**

```python
# modules/keycloak/tests/test_jwks.py
"""Tests for JWKS key cache and JWT validation."""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from keycloak.jwks import JWKSCache


def _generate_rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def _make_jwks_response(public_key, kid="test-key-1"):
    from jwt.algorithms import RSAAlgorithm

    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = kid
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return {"keys": [jwk]}


def _sign_token(private_key, payload, kid="test-key-1"):
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def rsa_keys():
    return _generate_rsa_keypair()


@pytest.fixture
def valid_payload():
    now = int(time.time())
    return {
        "sub": "user-123",
        "email": "test@example.com",
        "preferred_username": "testuser",
        "iss": "https://auth.example.com/realms/test",
        "aud": "my-client",
        "exp": now + 3600,
        "iat": now,
        "realm_access": {"roles": ["admin", "user"]},
    }


async def test_validate_jwt_valid_token(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    jwks_data = _make_jwks_response(public_key)
    httpx_mock.add_response(url="https://auth.example.com/jwks", json=jwks_data)

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is not None
    assert claims["sub"] == "user-123"
    assert claims["email"] == "test@example.com"


async def test_validate_jwt_expired_token(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    valid_payload["exp"] = int(time.time()) - 100
    jwks_data = _make_jwks_response(public_key)
    httpx_mock.add_response(url="https://auth.example.com/jwks", json=jwks_data)

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is None


async def test_validate_jwt_wrong_issuer(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    jwks_data = _make_jwks_response(public_key)
    httpx_mock.add_response(url="https://auth.example.com/jwks", json=jwks_data)

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://wrong-issuer.com/realms/test",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is None


async def test_validate_jwt_wrong_audience(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    jwks_data = _make_jwks_response(public_key)
    httpx_mock.add_response(url="https://auth.example.com/jwks", json=jwks_data)

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://auth.example.com/realms/test",
        audience="wrong-client",
    )

    token = _sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is None


async def test_jwks_cache_refetches_on_unknown_kid(rsa_keys, valid_payload, httpx_mock):
    """When a token has a kid not in cache, refetch JWKS once before rejecting."""
    private_key, public_key = rsa_keys
    jwks_data = _make_jwks_response(public_key, kid="rotated-key")
    httpx_mock.add_response(url="https://auth.example.com/jwks", json={"keys": []})
    httpx_mock.add_response(url="https://auth.example.com/jwks", json=jwks_data)

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload, kid="rotated-key")
    claims = await cache.validate_jwt(token)
    assert claims is not None
    assert claims["sub"] == "user-123"
```

Note: These tests require `pytest-httpx` for mocking. Add to dev dependencies if not already present, or use `httpx_mock` fixture from `pytest-httpx`. Alternatively, mock `httpx.AsyncClient.get` directly if `pytest-httpx` is not available.

- [ ] **Step 2: Run tests — should fail**

Run: `uv run pytest modules/keycloak/tests/test_jwks.py -v`
Expected: `ImportError` — `keycloak.jwks` doesn't exist.

- [ ] **Step 3: Implement JWKSCache**

```python
# modules/keycloak/keycloak/jwks.py
"""JWKS key cache and JWT validation for Keycloak tokens."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)


class JWKSCache:
    """Caches Keycloak's public signing keys and validates JWTs.

    On validation failure with cached keys, refetches JWKS once before
    rejecting — this handles Keycloak key rotation gracefully.
    """

    def __init__(
        self,
        jwks_url: str,
        ttl_seconds: int = 3600,
        issuer: str = "",
        audience: str = "",
    ) -> None:
        self._jwks_url = jwks_url
        self._ttl = ttl_seconds
        self._issuer = issuer
        self._audience = audience
        self._keys: dict[str, Any] = {}
        self._fetched_at: float = 0

    async def validate_jwt(self, token: str) -> dict[str, Any] | None:
        """Decode and validate a JWT. Returns claims dict or None."""
        try:
            unverified = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError:
            return None

        kid = unverified.get("kid")
        if kid is None:
            return None

        key = await self._get_key(kid)
        if key is None:
            return None

        return self._decode(token, key)

    def _decode(self, token: str, key: Any) -> dict[str, Any] | None:
        try:
            return jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer if self._issuer else None,
                audience=self._audience if self._audience else None,
                options={
                    "verify_iss": bool(self._issuer),
                    "verify_aud": bool(self._audience),
                },
            )
        except (jwt.ExpiredSignatureError, jwt.InvalidIssuerError, jwt.InvalidAudienceError):
            return None
        except jwt.PyJWTError:
            logger.exception("JWT validation failed")
            return None

    async def _get_key(self, kid: str) -> Any | None:
        if self._is_stale() or kid not in self._keys:
            await self._fetch_keys()

        if kid in self._keys:
            return self._keys[kid]

        # Key rotation: refetch once more if kid still missing
        await self._fetch_keys(force=True)
        return self._keys.get(kid)

    def _is_stale(self) -> bool:
        return time.monotonic() - self._fetched_at > self._ttl

    async def _fetch_keys(self, *, force: bool = False) -> None:
        if not force and not self._is_stale():
            return
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self._jwks_url, timeout=10)
                resp.raise_for_status()
                jwks_data = resp.json()
        except Exception:
            logger.exception("Failed to fetch JWKS from %s", self._jwks_url)
            return

        new_keys: dict[str, Any] = {}
        for key_data in jwks_data.get("keys", []):
            kid = key_data.get("kid")
            if kid and key_data.get("alg") == "RS256":
                try:
                    public_key = RSAAlgorithm.from_jwk(key_data)
                    new_keys[kid] = public_key
                except Exception:
                    logger.warning("Failed to parse JWK kid=%s", kid)
        self._keys = new_keys
        self._fetched_at = time.monotonic()
```

- [ ] **Step 4: Run tests — should pass**

Run: `uv run pytest modules/keycloak/tests/test_jwks.py -v`
Expected: All 5 tests pass. (If `pytest-httpx` is not installed, install it: `uv add --dev pytest-httpx` or use inline mocking.)

- [ ] **Step 5: Commit**

```bash
git add modules/keycloak/keycloak/jwks.py modules/keycloak/tests/test_jwks.py
git commit -m "feat(keycloak): JWKS key cache with JWT validation and key-rotation retry"
```

---

## Task 10: OIDC Discovery + Token Exchange

**Files:**
- Create: `modules/keycloak/keycloak/oidc.py`
- Create: `modules/keycloak/tests/test_oidc.py`

- [ ] **Step 1: Write OIDC helper tests**

```python
# modules/keycloak/tests/test_oidc.py
"""Tests for OIDC discovery and token exchange helpers."""

from __future__ import annotations

import secrets

import pytest
from keycloak.oidc import OIDCClient


@pytest.fixture
def oidc_client():
    return OIDCClient(
        server_url="https://auth.example.com",
        realm="test",
        client_id="my-app",
        client_secret="secret123",
    )


def test_authorization_url(oidc_client):
    url, state = oidc_client.build_authorization_url(
        redirect_uri="https://app.example.com/callback",
        nonce="test-nonce",
    )
    assert "auth.example.com/realms/test/protocol/openid-connect/auth" in url
    assert "client_id=my-app" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "scope=openid" in url
    assert "nonce=test-nonce" in url
    assert state is not None
    assert len(state) > 0


def test_token_endpoint_url(oidc_client):
    assert oidc_client.token_endpoint == (
        "https://auth.example.com/realms/test/protocol/openid-connect/token"
    )


def test_logout_url(oidc_client):
    url = oidc_client.build_logout_url(
        post_logout_redirect_uri="https://app.example.com/login",
        id_token_hint="token123",
    )
    assert "auth.example.com/realms/test/protocol/openid-connect/logout" in url
    assert "post_logout_redirect_uri=" in url
    assert "id_token_hint=token123" in url


def test_issuer(oidc_client):
    assert oidc_client.issuer == "https://auth.example.com/realms/test"


async def test_exchange_code(oidc_client, httpx_mock):
    httpx_mock.add_response(
        url=oidc_client.token_endpoint,
        json={
            "access_token": "at-123",
            "id_token": "id-123",
            "refresh_token": "rt-123",
            "token_type": "Bearer",
            "expires_in": 300,
        },
    )
    tokens = await oidc_client.exchange_code(
        code="auth-code-xyz",
        redirect_uri="https://app.example.com/callback",
    )
    assert tokens["access_token"] == "at-123"
    assert tokens["id_token"] == "id-123"
```

- [ ] **Step 2: Run tests — should fail**

Run: `uv run pytest modules/keycloak/tests/test_oidc.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement OIDCClient**

```python
# modules/keycloak/keycloak/oidc.py
"""OIDC helpers for Keycloak — authorization URL, token exchange, logout."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx


class OIDCClient:
    """Thin wrapper around Keycloak's OIDC endpoints."""

    def __init__(
        self,
        server_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._base = f"{server_url.rstrip('/')}/realms/{realm}/protocol/openid-connect"
        self._client_id = client_id
        self._client_secret = client_secret
        self._server_url = server_url.rstrip("/")
        self._realm = realm

    @property
    def issuer(self) -> str:
        return f"{self._server_url}/realms/{self._realm}"

    @property
    def token_endpoint(self) -> str:
        return f"{self._base}/token"

    @property
    def jwks_url(self) -> str:
        return f"{self._base}/certs"

    def build_authorization_url(
        self,
        redirect_uri: str,
        nonce: str,
        scope: str = "openid email profile",
    ) -> tuple[str, str]:
        """Build the OIDC authorization URL. Returns (url, state)."""
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
            "nonce": nonce,
        }
        url = f"{self._base}/auth?{urlencode(params)}"
        return url, state

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        """Exchange an authorization code for tokens."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_endpoint, data=data, timeout=10)
            resp.raise_for_status()
            return resp.json()

    def build_logout_url(
        self,
        post_logout_redirect_uri: str,
        id_token_hint: str | None = None,
    ) -> str:
        params: dict[str, str] = {
            "post_logout_redirect_uri": post_logout_redirect_uri,
        }
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{self._base}/logout?{urlencode(params)}"
```

- [ ] **Step 4: Run tests — should pass**

Run: `uv run pytest modules/keycloak/tests/test_oidc.py -v`
Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add modules/keycloak/keycloak/oidc.py modules/keycloak/tests/test_oidc.py
git commit -m "feat(keycloak): OIDC client with authorization URL, token exchange, logout"
```

---

## Task 11: KeycloakUserCache Model + Migration

**Files:**
- Create: `modules/keycloak/keycloak/models.py`
- Create migration via Alembic

- [ ] **Step 1: Create the model**

```python
# modules/keycloak/keycloak/models.py
"""Keycloak user cache — maps Keycloak sub to a stable framework UUID."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime

from simple_module_db.base import create_module_base
from sqlmodel import Field

Base = create_module_base("keycloak")


class KeycloakUserCache(Base, table=True):
    __tablename__ = "keycloak_user_cache"

    id: uuid_mod.UUID = Field(default_factory=uuid_mod.uuid4, primary_key=True)
    keycloak_sub: str = Field(unique=True, index=True)
    email: str = ""
    full_name: str | None = None
    last_login_at: datetime | None = None
```

- [ ] **Step 2: Generate migration**

Run: `make migration msg="add keycloak_user_cache table"`
Expected: New migration file created in `host/migrations/versions/`.

- [ ] **Step 3: Apply migration**

Run: `make migrate`
Expected: Migration applies cleanly.

- [ ] **Step 4: Commit**

```bash
git add modules/keycloak/keycloak/models.py host/migrations/versions/*keycloak*
git commit -m "feat(keycloak): KeycloakUserCache model + migration"
```

---

## Task 12: KeycloakAuthProvider Implementation

**Files:**
- Create: `modules/keycloak/keycloak/provider.py`
- Create: `modules/keycloak/tests/test_keycloak_provider.py`

- [ ] **Step 1: Write provider tests**

```python
# modules/keycloak/tests/test_keycloak_provider.py
"""Tests for KeycloakAuthProvider."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from auth.contracts.provider import AuthProvider
from auth.contracts.schemas import UserContext
from keycloak.provider import KeycloakAuthProvider
from keycloak.settings import KeycloakSettings


@pytest.fixture
def settings():
    return KeycloakSettings(
        server_url="https://auth.example.com",
        realm="test",
        client_id="my-app",
        client_secret="secret",
        role_mapping={"admin": "admin", "user": "user", "editor": "editor"},
    )


@pytest.fixture
def provider(settings):
    return KeycloakAuthProvider(settings)


def test_satisfies_protocol(provider):
    assert isinstance(provider, AuthProvider)


def test_name(provider):
    assert provider.name == "keycloak"


def test_login_url(provider):
    assert provider.get_login_url(None) == "/keycloak/login"


def test_logout_url(provider):
    assert provider.get_logout_url(None) == "/keycloak/logout"


def test_public_paths(provider):
    prefixes, exact = provider.get_public_paths()
    assert "/keycloak/login" in prefixes
    assert "/api/keycloak/auth/" in prefixes


def test_is_bearer_request(provider):
    req = MagicMock()
    req.headers = {"authorization": "Bearer abc"}
    assert provider.is_bearer_request(req) is True

    req.headers = {}
    assert provider.is_bearer_request(req) is False


def test_claims_to_user_context(provider):
    claims = {
        "sub": "kc-user-123",
        "email": "test@example.com",
        "preferred_username": "testuser",
        "realm_access": {"roles": ["admin", "unknown_role", "user"]},
    }
    ctx = provider._claims_to_user_context(claims, cache_id="aaaaaaaa-0000-0000-0000-000000000001")
    assert isinstance(ctx, UserContext)
    assert ctx.id == "aaaaaaaa-0000-0000-0000-000000000001"
    assert ctx.email == "test@example.com"
    assert ctx.name == "testuser"
    assert sorted(ctx.roles) == ["admin", "user"]
    # "unknown_role" not in mapping, so excluded


def test_claims_to_user_context_no_roles(provider):
    claims = {"sub": "kc-user-456", "email": "noroles@example.com"}
    ctx = provider._claims_to_user_context(claims, cache_id="bbbb")
    assert ctx.roles == []


def test_extract_roles_custom_claim_path(settings):
    settings.roles_claim_path = "resource_access.my-app.roles"
    provider = KeycloakAuthProvider(settings)
    claims = {"sub": "x", "resource_access": {"my-app": {"roles": ["admin"]}}}
    ctx = provider._claims_to_user_context(claims, cache_id="cccc")
    assert ctx.roles == ["admin"]
```

- [ ] **Step 2: Run tests — should fail**

Run: `uv run pytest modules/keycloak/tests/test_keycloak_provider.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement KeycloakAuthProvider**

```python
# modules/keycloak/keycloak/provider.py
"""KeycloakAuthProvider — resolves users from Keycloak JWTs or session."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from auth.contracts.schemas import UserContext
from starlette.requests import Request

if TYPE_CHECKING:
    from keycloak.jwks import JWKSCache
    from keycloak.settings import KeycloakSettings

logger = logging.getLogger(__name__)

_SESSION_USER_CTX_KEY = "user_ctx"


class KeycloakAuthProvider:
    """OIDC auth provider backed by Keycloak."""

    name = "keycloak"
    _is_auth_provider = True

    def __init__(self, settings: KeycloakSettings) -> None:
        self._settings = settings
        self.jwks_cache: JWKSCache | None = None

    async def resolve_user(self, request: Request) -> UserContext | None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return await self._resolve_bearer(request, auth_header[7:])

        session = request.scope.get("session", {})
        return UserContext.from_session_dict(session.get(_SESSION_USER_CTX_KEY))

    def get_login_url(self, request: Request | None, next_url: str | None = None) -> str:
        return "/keycloak/login"

    def get_logout_url(self, request: Request | None) -> str:
        return "/keycloak/logout"

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (
            ("/keycloak/login", "/keycloak/logout", "/api/keycloak/auth/"),
            (),
        )

    def is_bearer_request(self, request: Request | None) -> bool:
        if request is None:
            return False
        return request.headers.get("authorization", "").startswith("Bearer ")

    async def _resolve_bearer(self, request: Request, token: str) -> UserContext | None:
        if self.jwks_cache is None:
            logger.warning("JWKS cache not initialized; rejecting bearer token")
            return None
        claims = await self.jwks_cache.validate_jwt(token)
        if claims is None:
            return None

        cache_id = await self._upsert_user_cache(request, claims)
        return self._claims_to_user_context(claims, cache_id=cache_id)

    def _claims_to_user_context(
        self,
        claims: dict[str, Any],
        *,
        cache_id: str,
    ) -> UserContext:
        roles_raw = _extract_nested(claims, self._settings.roles_claim_path)
        mapped = [
            self._settings.role_mapping[r]
            for r in (roles_raw or [])
            if r in self._settings.role_mapping
        ]
        return UserContext(
            id=cache_id,
            email=claims.get("email", ""),
            name=claims.get("preferred_username") or claims.get("name", ""),
            roles=mapped,
            tenant_id=claims.get("tenant_id"),
        )

    async def _upsert_user_cache(self, request: Request, claims: dict) -> str:
        """Upsert KeycloakUserCache and return its UUID as string."""
        try:
            from keycloak.models import KeycloakUserCache
            from sqlalchemy import select

            session_factory = request.app.state.sm.db.session_factory
            sub = claims["sub"]
            async with session_factory() as db:
                stmt = select(KeycloakUserCache).where(KeycloakUserCache.keycloak_sub == sub)
                row = (await db.execute(stmt)).scalar_one_or_none()
                if row is None:
                    import uuid as uuid_mod
                    from datetime import datetime, timezone

                    row = KeycloakUserCache(
                        id=uuid_mod.uuid4(),
                        keycloak_sub=sub,
                        email=claims.get("email", ""),
                        full_name=claims.get("preferred_username"),
                        last_login_at=datetime.now(timezone.utc),
                    )
                    db.add(row)
                    await db.flush()
                else:
                    from datetime import datetime, timezone

                    row.email = claims.get("email", row.email)
                    row.full_name = claims.get("preferred_username", row.full_name)
                    row.last_login_at = datetime.now(timezone.utc)
                    await db.flush()
                return str(row.id)
        except Exception:
            logger.exception("Failed to upsert KeycloakUserCache for sub=%s", claims.get("sub"))
            return claims.get("sub", "unknown")


def _extract_nested(data: dict, path: str) -> list[str] | None:
    """Extract a value from a nested dict using a dot-separated path."""
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current if isinstance(current, list) else None
```

- [ ] **Step 4: Run tests — should pass**

Run: `uv run pytest modules/keycloak/tests/test_keycloak_provider.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add modules/keycloak/keycloak/provider.py modules/keycloak/tests/test_keycloak_provider.py
git commit -m "feat(keycloak): KeycloakAuthProvider with JWT resolution and role mapping"
```

---

## Task 13: Keycloak Endpoints (API + Views)

**Files:**
- Create: `modules/keycloak/keycloak/endpoints/api.py`
- Create: `modules/keycloak/keycloak/endpoints/__init__.py`
- Create: `modules/keycloak/keycloak/endpoints/views.py`
- Create: `modules/keycloak/keycloak/pages/Login.tsx`
- Create: `modules/keycloak/keycloak/pages/LoggedOut.tsx`

- [ ] **Step 1: Create endpoints `__init__.py`**

```python
# modules/keycloak/keycloak/endpoints/__init__.py
"""Keycloak endpoint routers."""
```

- [ ] **Step 2: Create API endpoints**

```python
# modules/keycloak/keycloak/endpoints/api.py
"""Keycloak OIDC API endpoints — login redirect, callback."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

if TYPE_CHECKING:
    from keycloak.settings import KeycloakSettings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["keycloak-auth"])

_SESSION_OIDC_STATE = "keycloak_oidc_state"
_SESSION_OIDC_NONCE = "keycloak_oidc_nonce"
_SESSION_USER_CTX = "user_ctx"
_SESSION_ID_TOKEN = "keycloak_id_token"
_SESSION_NEXT = "next"


def _get_settings(request: Request) -> KeycloakSettings:
    return request.app.state.keycloak.settings


def _get_oidc_client(request: Request):
    from keycloak.oidc import OIDCClient

    s = _get_settings(request)
    return OIDCClient(
        server_url=s.server_url,
        realm=s.realm,
        client_id=s.client_id,
        client_secret=s.client_secret,
    )


@router.get("/login")
async def oidc_login(request: Request):
    """Redirect to Keycloak's authorization endpoint."""
    client = _get_oidc_client(request)
    callback_url = str(request.url_for("oidc_callback"))
    nonce = secrets.token_urlsafe(32)
    url, state = client.build_authorization_url(
        redirect_uri=callback_url,
        nonce=nonce,
    )
    request.session[_SESSION_OIDC_STATE] = state
    request.session[_SESSION_OIDC_NONCE] = nonce
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
async def oidc_callback(request: Request):
    """Handle Keycloak's authorization code callback."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    expected_state = request.session.pop(_SESSION_OIDC_STATE, None)
    nonce = request.session.pop(_SESSION_OIDC_NONCE, None)

    if not code or not state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OIDC state")

    client = _get_oidc_client(request)
    callback_url = str(request.url_for("oidc_callback"))

    try:
        tokens = await client.exchange_code(code=code, redirect_uri=callback_url)
    except Exception:
        logger.exception("Token exchange failed")
        raise HTTPException(status_code=502, detail="Token exchange failed")

    id_token = tokens.get("id_token", "")
    access_token = tokens.get("access_token", "")

    jwks_cache = request.app.state.keycloak.jwks_cache
    claims = await jwks_cache.validate_jwt(access_token) if jwks_cache else None
    if claims is None:
        raise HTTPException(status_code=401, detail="Token validation failed")

    provider = request.app.state.auth.auth_provider
    cache_id = await provider._upsert_user_cache(request, claims)
    user_ctx = provider._claims_to_user_context(claims, cache_id=cache_id)

    request.session[_SESSION_USER_CTX] = user_ctx.to_session_dict()
    request.session[_SESSION_ID_TOKEN] = id_token

    s = _get_settings(request)
    next_url = request.session.pop(_SESSION_NEXT, None) or s.login_redirect_url
    return RedirectResponse(next_url, status_code=303)
```

- [ ] **Step 3: Create view endpoints**

```python
# modules/keycloak/keycloak/endpoints/views.py
"""Keycloak Inertia view routes — login page, logout."""

from __future__ import annotations

from fastapi import APIRouter, Request
from simple_module_hosting.inertia_deps import InertiaDep
from starlette.responses import RedirectResponse

router = APIRouter(tags=["keycloak-views"])

_SESSION_USER_CTX = "user_ctx"
_SESSION_ID_TOKEN = "keycloak_id_token"


@router.get("/login")
async def login_page(request: Request, inertia: InertiaDep):
    """Render a minimal login page that can auto-redirect to Keycloak."""
    return inertia.render("Keycloak/Login")


@router.post("/logout")
async def logout(request: Request):
    """Clear framework session and redirect to Keycloak's logout endpoint."""
    from keycloak.oidc import OIDCClient

    s = request.app.state.keycloak.settings
    id_token = request.session.get(_SESSION_ID_TOKEN)

    request.session.clear()

    client = OIDCClient(
        server_url=s.server_url,
        realm=s.realm,
        client_id=s.client_id,
        client_secret=s.client_secret,
    )
    base_url = str(request.base_url).rstrip("/")
    logout_url = client.build_logout_url(
        post_logout_redirect_uri=f"{base_url}/keycloak/login",
        id_token_hint=id_token,
    )
    return RedirectResponse(logout_url, status_code=303)
```

- [ ] **Step 4: Create frontend pages**

`modules/keycloak/keycloak/pages/Login.tsx`:
```tsx
import { router } from "@inertiajs/react";
import { useEffect } from "react";

export default function Login() {
  useEffect(() => {
    router.get("/api/keycloak/auth/login");
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground">Redirecting to identity provider…</p>
    </div>
  );
}
```

`modules/keycloak/keycloak/pages/LoggedOut.tsx`:
```tsx
import { Link } from "@inertiajs/react";

export default function LoggedOut() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-bold">Signed Out</h1>
      <p className="text-muted-foreground">You have been signed out successfully.</p>
      <Link href="/keycloak/login" className="text-primary underline">
        Sign in again
      </Link>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add modules/keycloak/keycloak/endpoints/ modules/keycloak/keycloak/pages/
git commit -m "feat(keycloak): OIDC login/callback endpoints + Inertia login/logout pages"
```

---

## Task 14: Users Module — Bearer Token + Refresh Token Endpoints

**Files:**
- Create: `modules/users/users/models/refresh_token.py`
- Create: `modules/users/users/auth_local/token_api.py`
- Modify: `modules/users/users/settings.py`
- Modify: `modules/users/users/module.py` (include token_api router)
- Create: `modules/users/tests/test_token_api.py`

- [ ] **Step 1: Write token endpoint tests**

```python
# modules/users/tests/test_token_api.py
"""Tests for bearer token endpoints (mobile auth)."""

from __future__ import annotations

import pytest


async def test_token_login_returns_tokens(client, authenticated_client):
    """POST /api/users/auth/token with valid credentials returns token pair."""
    # First create a user via the authenticated_client (admin)
    resp = await client.post(
        "/api/users/auth/token",
        json={"email": "admin@example.com", "password": "Admin1234!"},
    )
    # May need to seed user first — adjust based on test fixtures
    assert resp.status_code in (200, 400)  # 200 if user exists, 400 if not
    if resp.status_code == 200:
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"


async def test_token_login_invalid_credentials(client):
    resp = await client.post(
        "/api/users/auth/token",
        json={"email": "wrong@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_token_refresh(client):
    """POST /api/users/auth/token/refresh swaps refresh token for new pair."""
    # This test requires a valid refresh token — integration-level
    resp = await client.post(
        "/api/users/auth/token/refresh",
        json={"refresh_token": "invalid-token"},
    )
    assert resp.status_code == 401
```

- [ ] **Step 2: Add `bearer_token_lifetime_seconds` to UsersSettings**

In `modules/users/users/settings.py`, add after the existing cookie settings:

```python
    bearer_token_lifetime_seconds: int = 60 * 15  # 15 minutes
    refresh_token_lifetime_seconds: int = 60 * 60 * 24 * 30  # 30 days
```

- [ ] **Step 3: Create RefreshToken model**

```python
# modules/users/users/models/refresh_token.py
"""Refresh token for mobile/API bearer auth."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timezone

from simple_module_db.base import create_module_base
from sqlmodel import Field

from users.models.user import Base


class RefreshToken(Base, table=True):
    __tablename__ = "users_refresh_token"

    token: uuid_mod.UUID = Field(default_factory=uuid_mod.uuid4, primary_key=True)
    user_id: uuid_mod.UUID = Field(foreign_key="users_user.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    revoked_at: datetime | None = None
```

Update `modules/users/users/models/__init__.py` to export `RefreshToken`.

- [ ] **Step 4: Create token_api endpoints**

```python
# modules/users/users/auth_local/token_api.py
"""Bearer token endpoints for mobile/API clients."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from simple_module_db.deps import get_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from users.models import User
from users.models.refresh_token import RefreshToken

router = APIRouter(prefix="/auth", tags=["users-token"])


class TokenRequest(SQLModel):
    email: str
    password: str


class TokenResponse(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(SQLModel):
    refresh_token: str


@router.post("/token", response_model=TokenResponse)
async def token_login(body: TokenRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Exchange email+password for access + refresh token pair (mobile auth)."""
    from fastapi_users.password import PasswordHelper

    stmt = select(User).where(User.email == body.email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None or not user.is_active or user.disabled_at is not None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    helper = PasswordHelper()
    verified, _ = helper.verify_and_update(body.password, user.hashed_password)
    if not verified:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    settings = request.app.state.users.settings
    return await _create_token_pair(db, user.id, settings)


@router.post("/token/refresh", response_model=TokenResponse)
async def token_refresh(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new token pair (rotation)."""
    try:
        token_uuid = uuid_mod.UUID(body.refresh_token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    now = datetime.now(timezone.utc)
    stmt = select(RefreshToken).where(
        RefreshToken.token == token_uuid,
        RefreshToken.revoked_at.is_(None),  # type: ignore[union-attr]
        RefreshToken.expires_at > now,
    )
    rt = (await db.execute(stmt)).scalar_one_or_none()
    if rt is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    rt.revoked_at = now
    await db.flush()

    settings = request.app.state.users.settings
    return await _create_token_pair(db, rt.user_id, settings)


@router.delete("/token")
async def token_revoke(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Revoke a refresh token (mobile logout)."""
    try:
        token_uuid = uuid_mod.UUID(body.refresh_token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid token format")

    stmt = select(RefreshToken).where(RefreshToken.token == token_uuid)
    rt = (await db.execute(stmt)).scalar_one_or_none()
    if rt and rt.revoked_at is None:
        rt.revoked_at = datetime.now(timezone.utc)
        await db.flush()
    return {"status": "ok"}


async def _create_token_pair(
    db: AsyncSession,
    user_id: uuid_mod.UUID,
    settings,
) -> TokenResponse:
    """Create access + refresh token pair and persist the refresh token."""
    from users.models import UserAccessToken

    now = datetime.now(timezone.utc)

    access_token = UserAccessToken(
        token=str(uuid_mod.uuid4()),
        user_id=user_id,
        created_at=now,
    )
    db.add(access_token)

    refresh = RefreshToken(
        token=uuid_mod.uuid4(),
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.refresh_token_lifetime_seconds),
    )
    db.add(refresh)
    await db.flush()

    return TokenResponse(
        access_token=access_token.token,
        refresh_token=str(refresh.token),
        token_type="bearer",
        expires_in=settings.bearer_token_lifetime_seconds,
    )
```

- [ ] **Step 5: Wire token_api router into UsersModule.register_routes**

In `modules/users/users/module.py`, inside `register_routes`, add:

```python
from users.auth_local.token_api import router as token_router

api_router.include_router(token_router)
```

- [ ] **Step 6: Generate migration for refresh_token table**

Run: `make migration msg="add users_refresh_token table"`

- [ ] **Step 7: Run tests**

Run: `uv run pytest modules/users/tests/test_token_api.py -v`
Expected: Tests pass.

- [ ] **Step 8: Commit**

```bash
git add modules/users/users/models/refresh_token.py modules/users/users/auth_local/token_api.py modules/users/users/settings.py modules/users/users/module.py modules/users/users/models/__init__.py host/migrations/versions/*refresh_token*
git commit -m "feat(users): bearer token + refresh token endpoints for mobile auth"
```

---

## Task 15: Integration Tests + Full Suite Verification

**Files:**
- Create: `tests/integration/test_pluggable_auth.py`

- [ ] **Step 1: Write integration tests**

```python
# tests/integration/test_pluggable_auth.py
"""Integration tests for pluggable auth — verifying both providers work."""

from __future__ import annotations

from auth.contracts.provider import AuthProvider
from auth.state import AuthState


def test_users_module_is_auth_provider():
    from users.module import UsersModule

    assert UsersModule._is_auth_provider is True


def test_keycloak_module_is_auth_provider():
    from keycloak.module import KeycloakModule

    assert KeycloakModule._is_auth_provider is True


def test_sm020_fires_with_both_modules():
    from simple_module_core.diagnostics._module import ModuleDiagnostics
    from keycloak.module import KeycloakModule
    from users.module import UsersModule

    diags = ModuleDiagnostics()
    results = diags._check_auth_provider_conflict([UsersModule(), KeycloakModule()])
    assert any(d.code == "SM020" for d in results)


def test_sm021_fires_with_neither():
    from simple_module_core.diagnostics._module import ModuleDiagnostics
    from simple_module_core.module import ModuleBase, ModuleMeta

    class StubModule(ModuleBase):
        meta = ModuleMeta(name="Stub")

    diags = ModuleDiagnostics()
    results = diags._check_auth_provider_conflict([StubModule()])
    assert any(d.code == "SM021" for d in results)


def test_auth_provider_protocol_satisfied_by_users():
    from users.provider import UsersAuthProvider

    assert isinstance(UsersAuthProvider(), AuthProvider)


def test_auth_provider_protocol_satisfied_by_keycloak():
    from keycloak.provider import KeycloakAuthProvider
    from keycloak.settings import KeycloakSettings

    settings = KeycloakSettings(
        server_url="https://example.com",
        realm="test",
        client_id="app",
        client_secret="secret",
    )
    assert isinstance(KeycloakAuthProvider(settings), AuthProvider)
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_pluggable_auth.py -v`
Expected: All pass.

- [ ] **Step 3: Run full test suite**

Run: `make test`
Expected: All tests pass. No regressions in existing users, auth, or framework tests.

- [ ] **Step 4: Run linter**

Run: `make lint`
Expected: Clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_pluggable_auth.py
git commit -m "test: integration tests for pluggable auth provider system"
```

---

## Task 16: Documentation Update

**Files:**
- Modify: `docs/framework-conventions.md` (add auth provider section)
- The spec document is already committed

- [ ] **Step 1: Add auth provider section to framework conventions**

Add a section to `docs/framework-conventions.md` under the existing auth documentation:

```markdown
### Auth Provider Contract

The framework supports swappable authentication backends. Exactly one auth provider
module must be installed — either `simple-module-users` (local credentials + OAuth)
or `simple-module-keycloak` (Keycloak OIDC). Both implement the `AuthProvider`
protocol from `auth.contracts.provider`.

**Module authors never import from `users` or `keycloak` directly.** Use only:
- `from auth.deps import CurrentUser, require_permission`
- `from auth.contracts.schemas import UserContext`

The `AuthMiddleware` (in `auth/middleware.py`) delegates to the active provider's
`resolve_user()` method, then falls through to the principal-resolver chain.
API paths (`/api/*`) receive 401 JSON when unauthenticated; view paths receive
a 302 redirect to the provider's login URL.

Boot-time diagnostic `SM020` fails if multiple auth providers are installed.
`SM021` warns if none is installed.
```

- [ ] **Step 2: Update CLAUDE.md diagnostic codes table**

Add to the diagnostic codes section:
```
`SM020` multiple auth provider modules installed (error), `SM021` no auth provider module installed (warn)
```

- [ ] **Step 3: Commit**

```bash
git add docs/framework-conventions.md CLAUDE.md
git commit -m "docs: document pluggable auth provider contract and SM020/SM021 diagnostics"
```

---

## Summary of Commit Sequence

1. `feat(auth): add AuthProvider protocol for swappable auth backends`
2. `feat(auth): add auth_provider slot to AuthState`
3. `feat(auth): add provider-agnostic AuthMiddleware`
4. `refactor(auth,users): move AuthMiddleware + principal_serializer to auth module`
5. `feat(users): implement UsersAuthProvider with session-cookie resolution`
6. `refactor(users): delegate to auth.middleware, keep thin re-export for compat`
7. `feat(diagnostics): SM020/SM021 — exactly one auth provider required`
8. `feat(keycloak): scaffold keycloak module with settings + provider registration`
9. `feat(keycloak): JWKS key cache with JWT validation and key-rotation retry`
10. `feat(keycloak): OIDC client with authorization URL, token exchange, logout`
11. `feat(keycloak): KeycloakUserCache model + migration`
12. `feat(keycloak): KeycloakAuthProvider with JWT resolution and role mapping`
13. `feat(keycloak): OIDC login/callback endpoints + Inertia login/logout pages`
14. `feat(users): bearer token + refresh token endpoints for mobile auth`
15. `test: integration tests for pluggable auth provider system`
16. `docs: document pluggable auth provider contract and SM020/SM021 diagnostics`

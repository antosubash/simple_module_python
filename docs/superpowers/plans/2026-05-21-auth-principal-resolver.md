# Auth Principal-Resolver Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a principal-resolver chain on `app.state.auth` so downstream modules (e.g. `smpy_gis`) can plug in a PAT / bearer-token resolver alongside the existing session-cookie auth, with no changes to existing session-only consumers.

**Architecture:** New `PrincipalResolver` type + `AuthState` registry owned by the `auth` module. `users.AuthMiddleware` falls through `session-cookie → registered resolvers → unauthenticated`. Unauthenticated `/api/*` paths return 401 JSON; view paths still 302-redirect to `/users/login`. Resolvers are request-scoped (must not write the session).

**Tech Stack:** Python 3.12, FastAPI, Starlette, SQLModel, pytest-anyio, httpx (test client).

**Spec:** `docs/superpowers/specs/2026-05-21-auth-principal-resolver-design.md`

**Issue:** [#163](https://github.com/antosubash/simple_module_python/issues/163)

---

## File map

| Path | Action | Purpose |
|---|---|---|
| `modules/auth/auth/contracts/resolver.py` | Create | `PrincipalResolver` type alias + invariant docstring |
| `modules/auth/auth/state.py` | Create | `AuthState` dataclass (registry holder) |
| `modules/auth/auth/module.py` | Modify | Add `register_settings` that puts `AuthState` on `app.state.auth` |
| `modules/auth/auth/__init__.py` | Modify | Re-export `PrincipalResolver` and `UserContext` |
| `modules/auth/tests/test_resolver_registry.py` | Create | Unit tests for the registry + `register_settings` |
| `modules/users/users/middleware.py` | Modify | Resolver fall-through + 401-JSON-for-`/api/*` branch |
| `modules/users/tests/_middleware_support.py` | Modify | `_build_app` accepts optional resolvers and seeds `app.state.auth` |
| `modules/users/tests/test_users_middleware.py` | Modify | New tests: resolver flow + API-401 branch |
| `tests/test_principal_resolver_integration.py` | Create | End-to-end test against `create_app(settings)` with a fake bearer resolver |
| `docs/framework/principal-resolvers.md` | Create | Authoritative reference + worked Bearer-token example |
| `docs/framework-conventions.md` | Modify | One-paragraph pointer to the new doc |

---

## Task 1: Add the `PrincipalResolver` type alias

**Files:**
- Create: `modules/auth/auth/contracts/resolver.py`
- Test: `modules/auth/tests/test_resolver_registry.py` (first test)

- [ ] **Step 1: Write the failing test**

Create `modules/auth/tests/test_resolver_registry.py`:

```python
"""Tests for the auth.contracts.resolver type + AuthState registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from auth.contracts.resolver import PrincipalResolver
from auth.contracts.schemas import UserContext
from starlette.requests import Request


def test_principal_resolver_type_accepts_async_callable():
    """A typical resolver signature should satisfy the type alias at runtime.

    The alias is documentation + a checkable shape — we exercise the shape
    by constructing one and asserting it's a Callable that returns an
    awaitable.
    """

    async def fake_resolver(request: Request) -> UserContext | None:
        return None

    # Runtime — alias resolves to Callable[..., Awaitable[...]]
    resolver: PrincipalResolver = fake_resolver
    assert callable(resolver)
    # Sanity: the function actually returns an awaitable when called.
    from unittest.mock import MagicMock

    result = resolver(MagicMock(spec=Request))
    assert isinstance(result, Awaitable)
    result.close()  # don't leave an unawaited coroutine
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest modules/auth/tests/test_resolver_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auth.contracts.resolver'`.

- [ ] **Step 3: Create the resolver module**

Create `modules/auth/auth/contracts/resolver.py`:

```python
"""Principal-resolver extension point — apps register additional auth sources here.

A ``PrincipalResolver`` is an async callable that inspects an incoming
``Request`` and returns a :class:`~auth.contracts.schemas.UserContext` if it
can authenticate the caller, or ``None`` to fall through to the next resolver
in the chain.

The chain is consulted by ``users.middleware.AuthMiddleware`` *after* the
session-cookie path has been tried, in registration order, and the first
non-``None`` return wins.

Invariants every resolver MUST satisfy:

* **Async.** Resolvers are awaited.
* **Cheap fast-path bail.** Resolvers run on every request; return ``None``
  immediately when the credential type isn't present (e.g., no ``Authorization``
  header, no matching scheme).
* **Self-checks active/disabled state.** The middleware does NOT re-validate
  the user after the resolver returns — return ``None`` for disabled,
  unverified, or otherwise blocked users.
* **Never raise on bad credentials.** Return ``None`` and let the chain
  continue. The middleware wraps each resolver in ``try/except`` for
  defense in depth, but resolver authors should not rely on it.
* **Request-scoped — no session writes.** A PAT call must not silently
  elevate to a long-lived session cookie. If the resolver needs to mint a
  session, that's an entirely separate code path (the standard login flow).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request

from auth.contracts.schemas import UserContext

PrincipalResolver = Callable[[Request], Awaitable[UserContext | None]]
"""Async callable: ``(Request) -> UserContext | None``. See module docstring
for the invariants resolver authors must uphold."""

__all__ = ["PrincipalResolver"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest modules/auth/tests/test_resolver_registry.py -v`
Expected: PASS — single test green.

- [ ] **Step 5: Commit**

```bash
git add modules/auth/auth/contracts/resolver.py modules/auth/tests/test_resolver_registry.py
git commit -m "feat(auth): add PrincipalResolver type alias for credential-chain extension"
```

---

## Task 2: Add the `AuthState` dataclass

**Files:**
- Create: `modules/auth/auth/state.py`
- Test: `modules/auth/tests/test_resolver_registry.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `modules/auth/tests/test_resolver_registry.py`:

```python
def test_auth_state_initializes_with_empty_resolvers():
    from auth.state import AuthState

    state = AuthState()
    assert state.principal_resolvers == []


def test_auth_state_resolvers_is_mutable_list():
    """Modules register resolvers by appending; the list must be a list, not a tuple."""
    from auth.state import AuthState

    state = AuthState()

    async def resolver(request):  # pragma: no cover - registration smoke only
        return None

    state.principal_resolvers.append(resolver)
    assert state.principal_resolvers == [resolver]
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `uv run pytest modules/auth/tests/test_resolver_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auth.state'`.

- [ ] **Step 3: Create `state.py`**

Create `modules/auth/auth/state.py`:

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

- [ ] **Step 4: Run the suite to verify all tests pass**

Run: `uv run pytest modules/auth/tests/test_resolver_registry.py -v`
Expected: PASS — three tests green.

- [ ] **Step 5: Commit**

```bash
git add modules/auth/auth/state.py modules/auth/tests/test_resolver_registry.py
git commit -m "feat(auth): add AuthState registry for principal-resolvers"
```

---

## Task 3: Wire `AuthModule.register_settings`

**Files:**
- Modify: `modules/auth/auth/module.py`
- Test: `modules/auth/tests/test_resolver_registry.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `modules/auth/tests/test_resolver_registry.py`:

```python
def test_auth_module_register_settings_populates_app_state():
    """``AuthModule.register_settings(app)`` must put an AuthState on ``app.state.auth``."""
    from fastapi import FastAPI

    from auth.module import AuthModule
    from auth.state import AuthState

    app = FastAPI()
    AuthModule().register_settings(app)

    assert isinstance(app.state.auth, AuthState)
    assert app.state.auth.principal_resolvers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest modules/auth/tests/test_resolver_registry.py::test_auth_module_register_settings_populates_app_state -v`
Expected: FAIL with `AttributeError: 'State' object has no attribute 'auth'` (because `register_settings` is the no-op default from `ModuleBase`).

- [ ] **Step 3: Add `register_settings` to `AuthModule`**

Modify `modules/auth/auth/module.py` — add the new hook just before `locale_dirs`:

```python
"""Auth module — shared contracts (UserContext, deps).

Intentionally minimal: this module owns the PUBLIC interface (UserContext,
PrincipalResolver, get_current_user, CurrentUser, require_permission) that
every other module imports. Keeping it stable prevents churn when auth
internals change.

All authentication logic (middleware, login, signup, OAuth) lives in the
users module. The ``principal_resolvers`` registry on ``app.state.auth`` is
the extension point downstream modules use to plug in additional credential
sources (PAT bearer tokens, API keys, etc.) — see
``docs/framework/principal-resolvers.md`` for the worked example.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.module import ModuleBase, ModuleMeta

if TYPE_CHECKING:
    from fastapi import FastAPI


class AuthModule(ModuleBase):
    meta = ModuleMeta(
        name="Auth",
        route_prefix="/auth",
    )

    def register_settings(self, app: FastAPI) -> None:
        from auth.state import AuthState

        app.state.auth = AuthState()

    def locale_dirs(self) -> dict[str, Path]:
        return {"auth": Path(str(importlib.resources.files(__package__) / "locales"))}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest modules/auth/tests/test_resolver_registry.py modules/auth/tests/test_module.py -v`
Expected: PASS — all four resolver tests + the three existing module tests stay green.

- [ ] **Step 5: Commit**

```bash
git add modules/auth/auth/module.py modules/auth/tests/test_resolver_registry.py
git commit -m "feat(auth): seed app.state.auth with AuthState in register_settings"
```

---

## Task 4: Re-export the public surface from `auth/__init__.py`

**Files:**
- Modify: `modules/auth/auth/__init__.py`
- Test: `modules/auth/tests/test_resolver_registry.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `modules/auth/tests/test_resolver_registry.py`:

```python
def test_auth_package_reexports_public_surface():
    """Downstream authors should be able to ``from auth import PrincipalResolver, UserContext``."""
    import auth

    assert hasattr(auth, "PrincipalResolver")
    assert hasattr(auth, "UserContext")
    assert "PrincipalResolver" in auth.__all__
    assert "UserContext" in auth.__all__

    # Identity check — re-exports point at the canonical definitions.
    from auth.contracts.resolver import PrincipalResolver
    from auth.contracts.schemas import UserContext

    assert auth.PrincipalResolver is PrincipalResolver
    assert auth.UserContext is UserContext
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest modules/auth/tests/test_resolver_registry.py::test_auth_package_reexports_public_surface -v`
Expected: FAIL with `AssertionError` (no `PrincipalResolver` attribute on the `auth` package — its `__init__.py` is currently just a docstring).

- [ ] **Step 3: Add the re-exports**

Overwrite `modules/auth/auth/__init__.py`:

```python
"""Auth module — shared contracts (UserContext, PrincipalResolver, deps)."""

from auth.contracts.resolver import PrincipalResolver
from auth.contracts.schemas import UserContext

__all__ = ["PrincipalResolver", "UserContext"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest modules/auth/tests/test_resolver_registry.py -v`
Expected: PASS — all five tests green.

- [ ] **Step 5: Commit**

```bash
git add modules/auth/auth/__init__.py modules/auth/tests/test_resolver_registry.py
git commit -m "feat(auth): re-export PrincipalResolver + UserContext from package root"
```

---

## Task 5: Update `_middleware_support` to seed `app.state.auth`

**Files:**
- Modify: `modules/users/tests/_middleware_support.py`

The middleware change in Task 6 will read `app.state.auth.principal_resolvers`. We update the test helper first so every existing middleware test keeps passing once the middleware lands, and so new tests can register resolvers via a keyword arg.

- [ ] **Step 1: Modify `_build_app` to accept resolvers and seed `app.state.auth`**

Edit `modules/users/tests/_middleware_support.py` — replace the `_build_app` function with:

```python
async def _build_app(db_state, inner_handler=None, *, principal_resolvers=None):
    """Build a minimal ASGI app with AuthMiddleware + SessionMiddleware.

    ``principal_resolvers`` (optional) is a list of resolvers seeded onto
    ``app.state.auth.principal_resolvers`` before the middleware runs.
    Defaults to an empty registry — matches a production app where no
    downstream module has registered anything.
    """
    from auth.state import AuthState

    async def _default_handler(request: Request):
        user = getattr(request.state, "user", None)
        return JSONResponse(
            {
                "path": request.url.path,
                "user": (
                    {
                        "id": user.id,
                        "email": user.email,
                        "name": user.name,
                        "roles": user.roles,
                        "tenant_id": user.tenant_id,
                    }
                    if user is not None
                    else None
                ),
            }
        )

    handler = inner_handler or _default_handler

    app = FastAPI()
    app.state.sm = SimpleNamespace(db=db_state)
    app.state.auth = AuthState(
        principal_resolvers=list(principal_resolvers or []),
    )

    @app.get("/{path:path}")
    async def _catch_all(request: Request, path: str = ""):
        return await handler(request)

    # Middleware is applied in reverse order: SessionMiddleware outermost.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
    return app
```

- [ ] **Step 2: Confirm the existing middleware suite still passes**

Run: `uv run pytest modules/users/tests/test_users_middleware.py modules/users/tests/test_users_middleware_public_paths.py -v`
Expected: PASS — no behavior change yet (resolver registry is empty; AuthMiddleware hasn't been touched).

- [ ] **Step 3: Commit**

```bash
git add modules/users/tests/_middleware_support.py
git commit -m "test(users): seed app.state.auth in middleware test helper"
```

---

## Task 6: Add resolver fall-through + 401-for-`/api/*` to `AuthMiddleware`

**Files:**
- Modify: `modules/users/users/middleware.py`
- Test: `modules/users/tests/test_users_middleware.py` (append)

We write the full suite of middleware tests for the new behavior first, then implement.

- [ ] **Step 1: Write the failing tests**

Append the following section to `modules/users/tests/test_users_middleware.py` (just before any final pytest module-level fixtures, or at the bottom — order doesn't matter):

```python
# ---------------------------------------------------------------------------
# Principal-resolver chain
# ---------------------------------------------------------------------------


def _ctx(uid: str = "11111111-1111-1111-1111-111111111111", **overrides):
    """Build a UserContext for resolver tests."""
    from auth.contracts.schemas import UserContext

    fields = dict(
        id=uid,
        email="pat@example.com",
        name="PAT User",
        roles=["user"],
        tenant_id=None,
    )
    fields.update(overrides)
    return UserContext(**fields)


@pytest.mark.anyio
async def test_resolver_returning_context_authenticates_request(db_state):
    """A registered resolver that returns a UserContext authenticates the request."""

    async def stub_resolver(request):
        return _ctx()

    app = await _build_app(db_state, principal_resolvers=[stub_resolver])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard")

    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["email"] == "pat@example.com"


@pytest.mark.anyio
async def test_resolver_first_non_none_wins(db_state):
    """The first resolver returning a context wins; later resolvers are not consulted."""
    second_called = False

    async def first_none(request):
        return None

    async def second_returns(request):
        nonlocal second_called
        second_called = True
        return _ctx(email="second@example.com")

    async def third_should_not_run(request):
        raise AssertionError("third resolver should not run after a match")

    app = await _build_app(
        db_state,
        principal_resolvers=[first_none, second_returns, third_should_not_run],
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard")

    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "second@example.com"
    assert second_called


@pytest.mark.anyio
async def test_all_resolvers_return_none_falls_through_to_redirect(db_state):
    """When every resolver returns None for a view route → 302 to /users/login."""

    async def none_resolver(request):
        return None

    app = await _build_app(db_state, principal_resolvers=[none_resolver])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/users/login"


@pytest.mark.anyio
async def test_resolver_raising_does_not_crash_middleware(db_state, caplog):
    """A resolver that raises is logged and the chain continues to the next."""
    import logging

    async def boom(request):
        raise RuntimeError("resolver kaboom")

    async def fallback(request):
        return _ctx(email="fallback@example.com")

    app = await _build_app(db_state, principal_resolvers=[boom, fallback])
    transport = httpx.ASGITransport(app=app)
    with caplog.at_level(logging.ERROR, logger="users.middleware"):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/dashboard")

    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "fallback@example.com"
    assert any("resolver" in rec.message.lower() for rec in caplog.records)


@pytest.mark.anyio
async def test_api_path_unauthenticated_returns_401_json(db_state):
    """Unauthenticated /api/private should return 401 JSON, not a 302 redirect."""
    app = await _build_app(db_state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/private-thing", follow_redirects=False)

    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": "Not authenticated"}


@pytest.mark.anyio
async def test_view_path_unauthenticated_still_redirects(db_state):
    """View routes (non-/api/*) keep the existing 302-to-login behavior."""
    app = await _build_app(db_state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/users/login"


@pytest.mark.anyio
async def test_session_wins_over_resolver(db_state, mw_active_user):
    """A valid session cookie short-circuits — the resolver chain is not consulted."""
    resolver_called = False

    async def should_not_run(request):
        nonlocal resolver_called
        resolver_called = True
        return _ctx(email="should-not-win@example.com")

    app = await _build_app(db_state, principal_resolvers=[should_not_run])
    transport = httpx.ASGITransport(app=app)
    cookies = _session_cookie({"user_id": str(mw_active_user.id)})
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies=cookies
    ) as client:
        resp = await client.get("/dashboard")

    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "middleware-test@example.com"
    assert resolver_called is False


@pytest.mark.anyio
async def test_resolver_does_not_write_session(db_state):
    """Resolver-authenticated requests must not persist anything to the session."""
    captured = {}

    async def capture(request: Request):
        captured["session"] = dict(request.session)
        user = getattr(request.state, "user", None)
        return JSONResponse({"authenticated": user is not None})

    async def stub_resolver(request):
        return _ctx()

    app = await _build_app(db_state, capture, principal_resolvers=[stub_resolver])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard")

    assert resp.status_code == 200
    assert resp.json() == {"authenticated": True}
    # Session must not contain a user_id, user_ctx, or anything resolver-added.
    assert "user_id" not in captured["session"]
    assert "user_ctx" not in captured["session"]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest modules/users/tests/test_users_middleware.py -v -k "resolver or api_path or view_path or session_wins"`
Expected: most/all of the eight new tests FAIL — `test_resolver_returning_context_authenticates_request` will redirect (302) instead of 200, `test_api_path_unauthenticated_returns_401_json` will get 302 not 401, etc.

- [ ] **Step 3: Update `AuthMiddleware`**

Modify `modules/users/users/middleware.py`. Two changes inside `AuthMiddleware.__call__`:

**(a)** Replace the import block at the top of the file. Add `JSONResponse`:

```python
from starlette.responses import JSONResponse, RedirectResponse
```

**(b)** Replace the body of `__call__` from the `session = scope["session"]` line through the end of the `if user_ctx is None and not is_public:` block with the version below. The DB-load fast path, `request.state.user` assignment, and `current_user_id` ContextVar lifecycle stay exactly as they were.

```python
session = scope["session"]
raw_user_id = session.get(_SESSION_USER_ID_KEY)

user_ctx: UserContext | None = None
if raw_user_id:
    user_id_str = str(raw_user_id)
    # Fast path — rebuild from the signed session cookie.
    user_ctx = UserContext.from_session_dict(session.get(SESSION_USER_CTX_KEY))
    if user_ctx is None or user_ctx.id != user_id_str:
        try:
            user_uuid = uuid.UUID(user_id_str)
        except (ValueError, TypeError):
            logger.warning("Invalid user_id in session: %r", raw_user_id)
            session.pop(_SESSION_USER_ID_KEY, None)
            session.pop(SESSION_USER_CTX_KEY, None)
            user_ctx = None
        else:
            user_ctx = await self._load_user(scope, user_uuid)
            if user_ctx is None:
                # User was deleted / disabled since session creation.
                session.pop(_SESSION_USER_ID_KEY, None)
                session.pop(SESSION_USER_CTX_KEY, None)
            else:
                session[SESSION_USER_CTX_KEY] = user_ctx.to_session_dict()

# Fall-through: registered principal resolvers (PAT, API key, ...).
# The session-cookie path above is authoritative; resolvers only run
# when no session-authenticated user was resolved.
if user_ctx is None:
    auth_state = getattr(scope["app"].state, "auth", None)
    resolvers = getattr(auth_state, "principal_resolvers", ()) if auth_state else ()
    if resolvers:
        request = Request(scope)
        for resolver in resolvers:
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
    if path.startswith("/api/"):
        response = JSONResponse({"detail": "Not authenticated"}, status_code=401)
    else:
        request = Request(scope)
        session[_SESSION_NEXT_KEY] = str(request.url)
        response = RedirectResponse(_LOGIN_REDIRECT, status_code=302)
    await response(scope, receive, send)
    return
```

(Everything after this block — the `if user_ctx is not None:` setting `request.state.user` and managing `current_user_id` — stays exactly as today.)

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest modules/users/tests/test_users_middleware.py -v`
Expected: PASS — both the eight new resolver/API tests AND every pre-existing middleware test stay green.

- [ ] **Step 5: Run the entire users test directory to catch any collateral damage**

Run: `uv run pytest modules/users/tests/ -q`
Expected: PASS — no regressions in the OAuth, bootstrap, admin, public-paths, or other suites.

- [ ] **Step 6: Commit**

```bash
git add modules/users/users/middleware.py modules/users/tests/test_users_middleware.py
git commit -m "feat(users): consult app.state.auth.principal_resolvers + 401-JSON for /api/*"
```

---

## Task 7: End-to-end integration test

**Files:**
- Create: `tests/test_principal_resolver_integration.py`

This exercises the full `create_app(settings)` boot path — `AuthModule.register_settings` runs, `UsersModule.register_middleware` installs `AuthMiddleware`, and a resolver registered before the first request is consulted.

- [ ] **Step 1: Write the failing test**

Create `tests/test_principal_resolver_integration.py`:

```python
"""End-to-end test: a fake bearer-token resolver authenticates against the full app stack."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from auth.contracts.schemas import UserContext


@pytest.fixture
async def app_with_pat_resolver(app):
    """Reuses the standard ``app`` fixture and appends a fake bearer-token resolver.

    The resolver recognizes a single hardcoded token ``"good"`` mapped to a
    deterministic UserContext. ``"bad"`` (or absent header) returns None.
    """

    async def fake_pat_resolver(request) -> UserContext | None:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header.removeprefix("Bearer ")
        if token != "good":
            return None
        return UserContext(
            id="22222222-2222-2222-2222-222222222222",
            email="pat-user@example.com",
            name="PAT User",
            roles=["admin"],
            tenant_id=None,
        )

    app.state.auth.principal_resolvers.append(fake_pat_resolver)
    yield app
    app.state.auth.principal_resolvers.remove(fake_pat_resolver)


@pytest.fixture
async def pat_client(app_with_pat_resolver) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app_with_pat_resolver)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.mark.anyio
async def test_bearer_token_authenticates_against_protected_view(pat_client):
    """Valid bearer token → 200 on a protected view path (users admin)."""
    resp = await pat_client.get(
        "/users/admin",
        headers={"Authorization": "Bearer good"},
        follow_redirects=False,
    )
    # /users/admin is a view route; with a valid resolver the request gets
    # through AuthMiddleware (200) instead of redirecting to /users/login.
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_invalid_bearer_token_returns_401_on_api_path(pat_client):
    """Bad bearer on an /api/* path → 401 JSON, not a redirect."""
    resp = await pat_client.get(
        "/api/users/admin/users",
        headers={"Authorization": "Bearer bad"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not authenticated"}


@pytest.mark.anyio
async def test_no_auth_header_on_api_returns_401(pat_client):
    """No Authorization header on a private /api/* path → 401 JSON."""
    resp = await pat_client.get("/api/users/admin/users", follow_redirects=False)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not authenticated"}


@pytest.mark.anyio
async def test_session_wins_over_bad_bearer(authenticated_client):
    """A valid session cookie + Bearer bad → 200 via session; resolver not consulted.

    The ``authenticated_client`` fixture already carries an admin session cookie;
    here we additionally send a bad bearer to prove the session path wins."""
    resp = await authenticated_client.get(
        "/api/users/admin/users",
        headers={"Authorization": "Bearer bad"},
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run the new tests**

Run: `uv run pytest tests/test_principal_resolver_integration.py -v`
Expected: PASS — four green tests.

If a test fails with "Authorization header was rejected by an inner FastAPI dependency": adjust the target URL to a permission-protected endpoint that doesn't require additional dependency-injected arguments. `/api/users/admin/users` is a known admin route (see `modules/users/users/admin/api.py`); if its actual prefix differs, run `git grep 'admin_router' modules/users/` to locate the right URL and update the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_principal_resolver_integration.py
git commit -m "test: end-to-end integration test for principal-resolver chain"
```

---

## Task 8: Authoritative documentation

**Files:**
- Create: `docs/framework/principal-resolvers.md`

- [ ] **Step 1: Write the new doc**

Create `docs/framework/principal-resolvers.md`:

````markdown
# Principal-resolver chain

The `auth` module exposes an extension point — a list of async resolvers on
`app.state.auth.principal_resolvers` — that lets downstream modules plug in
additional credential sources alongside the built-in session cookie. This is
the supported way to add Personal Access Tokens, API keys, JWT bearers, or
any other request-scoped authentication scheme without forking
`users.AuthMiddleware`.

## The contract

```python
from collections.abc import Awaitable, Callable
from starlette.requests import Request
from auth import PrincipalResolver, UserContext

PrincipalResolver = Callable[[Request], Awaitable[UserContext | None]]
```

A resolver MUST:

- Be **async** (it is awaited by the middleware).
- **Bail fast** when its credential type isn't present (e.g., return `None`
  immediately if there is no `Authorization` header) — resolvers run on
  every request, including completely unauthenticated ones.
- **Self-check active / disabled state** before returning a `UserContext`.
  The middleware does not re-validate.
- **Never raise** on bad credentials — return `None` so the chain continues
  to the next resolver. The middleware swallows exceptions defensively but
  resolver authors should not rely on it.
- **Not write to the session.** Resolver-authenticated requests are
  per-request only; they never silently elevate into a long-lived session
  cookie. (To mint a session, use the standard login flow.)

## Resolution order

`users.AuthMiddleware` consults credential sources in this order:

1. **Session cookie** — the existing fast/cached path. If the session
   carries a valid `user_id` (and matching cached `user_ctx`), the user is
   authenticated and the resolver chain is **not** consulted.
2. **Registered resolvers**, in registration order. The first non-`None`
   return wins.
3. **Unauthenticated** — for `/api/*` paths the middleware returns
   `401 {"detail": "Not authenticated"}`; for view paths it 302-redirects to
   `/users/login` and stashes the original URL in `session["next"]`.

## Worked example — bearer-token resolver

A module that ships its own Personal-Access-Token table registers a
resolver from its `on_startup` hook:

```python
# modules/example/example/module.py
from __future__ import annotations

from typing import TYPE_CHECKING

from auth import PrincipalResolver, UserContext
from simple_module_core.module import ModuleBase, ModuleMeta
from starlette.requests import Request

if TYPE_CHECKING:
    from fastapi import FastAPI


class ExampleModule(ModuleBase):
    meta = ModuleMeta(name="Example", depends_on=["Auth", "Users"])

    async def on_startup(self, app: FastAPI) -> None:
        app.state.auth.principal_resolvers.append(self._build_pat_resolver(app))

    @staticmethod
    def _build_pat_resolver(app: FastAPI) -> PrincipalResolver:
        async def resolve_pat(request: Request) -> UserContext | None:
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return None
            token = header.removeprefix("Bearer ")

            # Look up the token in the module's own storage and load the user.
            async with app.state.sm.db.session_factory() as session:
                record = await find_active_token(session, token)
                if record is None:
                    return None
                user = await load_user_with_roles(session, record.user_id)
                if user is None or not user.is_active or user.disabled_at is not None:
                    return None
                return UserContext.from_user(user)

        return resolve_pat
```

`depends_on=["Auth", "Users"]` ensures `AuthModule.register_settings` has
run (so `app.state.auth` exists) and `UsersModule.register_middleware` has
installed `AuthMiddleware` (which calls the resolvers).

## When NOT to write a resolver

- **You want to mint a long-lived session.** Use the standard login flow
  (`/users/login` or OAuth). Resolvers are explicitly forbidden from
  writing the session.
- **You only need a per-endpoint API-key check.** A FastAPI dependency
  (`require_api_key`) on the route signature is simpler and keeps the
  authenticated-user shape clean.
- **You want to override the `users` module's behavior** (e.g., reject
  active users, change role semantics). Resolvers add credential sources;
  they don't change the rules of authentication. For that, swap
  `UsersModule`/`AuthMiddleware` outright.

## Testing your resolver

Write resolver tests against a minimal app (see
`modules/users/tests/_middleware_support.py::_build_app` for the pattern
used by the framework's own resolver suite — it takes a
`principal_resolvers=` keyword and seeds `app.state.auth` for you).

End-to-end tests should drive the full `create_app(settings)` stack and
append your resolver to `app.state.auth.principal_resolvers` in a fixture —
see `tests/test_principal_resolver_integration.py` for a worked example.
````

- [ ] **Step 2: Commit**

```bash
git add docs/framework/principal-resolvers.md
git commit -m "docs(framework): add principal-resolver chain reference"
```

---

## Task 9: Pointer from `framework-conventions.md`

**Files:**
- Modify: `docs/framework-conventions.md`

- [ ] **Step 1: Locate the auth section**

Run: `grep -n -i "auth\|principal\|session" docs/framework-conventions.md | head -20`

Identify a sensible location near the existing auth/session discussion. If there is no dedicated auth section, append a new "Authentication extension points" section at the end of the document.

- [ ] **Step 2: Add a pointer paragraph**

Add this paragraph (adjust the surrounding heading level to match the file's style):

```markdown
### Authentication extension points

The `auth` module exposes a principal-resolver chain on
`app.state.auth.principal_resolvers` — a list of async callables that
`users.AuthMiddleware` consults after the session-cookie path. Use it to add
non-cookie credential sources (Personal Access Tokens, API keys, JWTs)
without forking the middleware. See
[`docs/framework/principal-resolvers.md`](framework/principal-resolvers.md)
for the contract, ordering rules, and a worked Bearer-token example.
```

- [ ] **Step 3: Commit**

```bash
git add docs/framework-conventions.md
git commit -m "docs: link framework-conventions to the principal-resolver reference"
```

---

## Task 10: Final verification — lint, doctor, full test suite

**Files:** none

- [ ] **Step 1: Run lint**

Run: `make lint`
Expected: PASS — Ruff format-check, Ruff, `ty`, Biome, `tsc`, and the 300-line file-size check all green. If `ty` flags the new resolver type, double-check the alias is importable from a stable path; if Ruff flags an unused import, prune it.

- [ ] **Step 2: Run module-doctor**

Run: `make doctor`
Expected: no new `SM*` errors. Specifically:
- `SM007` (module overrides no hooks) should NOT fire for `Auth` — `register_settings` is now overridden.
- `SM012` (`register_settings` overridden but nothing on `app.state.<module>`) should NOT fire — we set `app.state.auth`.
- All other codes unaffected by this change.

- [ ] **Step 3: Run the full Python test suite**

Run: `make test-py`
Expected: PASS — no regressions across `framework/`, `modules/`, or root `tests/`.

- [ ] **Step 4: Confirm the commit log**

Run: `git log --oneline -15`
Expected: roughly nine commits since the spec — one per task (1-3 from Task 1, 2, 3; one each from Tasks 4-9). If any task left uncommitted changes, commit them now with an appropriate message before opening the PR.

- [ ] **Step 5: Open the PR**

The branch is `worktree-issue-163-principal-resolver-spec`. Push and open the PR:

```bash
git push -u origin worktree-issue-163-principal-resolver-spec
gh pr create --title "feat(auth): principal-resolver chain for session-or-bearer auth (#163)" --body "$(cat <<'EOF'
## Summary
- Adds `app.state.auth.principal_resolvers`, an extension point for plugging in non-cookie auth (PAT bearer tokens, API keys, JWT, etc.) — closes #163.
- `users.AuthMiddleware` now falls through `session cookie → registered resolvers → unauthenticated`; unauthenticated `/api/*` returns `401 {"detail": "Not authenticated"}`, view paths still 302 to `/users/login`.
- New authoritative doc at `docs/framework/principal-resolvers.md` with a worked Bearer-token example.

## Test plan
- [x] `uv run pytest modules/auth/tests/test_resolver_registry.py -v`
- [x] `uv run pytest modules/users/tests/test_users_middleware.py -v`
- [x] `uv run pytest tests/test_principal_resolver_integration.py -v`
- [x] `make lint`
- [x] `make doctor`
- [x] `make test-py`
EOF
)"
```

---

## Self-review (engineer should re-skim before starting Task 1)

- **Spec coverage** — every section in `docs/superpowers/specs/2026-05-21-auth-principal-resolver-design.md` maps to a task here:
  - Architecture → Tasks 1-4 (types, state, module hook, re-exports).
  - Middleware changes (resolver fall-through + 401 for `/api/*`) → Task 6.
  - Test list → Tasks 5 (helper setup) + 6 (middleware tests) + 7 (integration).
  - Docs section → Tasks 8 + 9.
  - "Behavior changes for existing deployments" — covered by the `test_api_path_unauthenticated_returns_401_json` + `test_view_path_unauthenticated_still_redirects` pair in Task 6, plus the full middleware suite re-run in Task 6 Step 5.
  - "Out of scope" — by construction, nothing in this plan adds PAT models, caching, priority controls, or session-writing resolvers.

- **Placeholder scan** — every code step ships the actual code. No TBDs, no "similar to above", no "add error handling".

- **Type consistency** — `PrincipalResolver`, `AuthState`, `UserContext` are named identically across every task; `principal_resolvers` (snake_case, plural) is consistent everywhere; the resolver signature `(Request) -> Awaitable[UserContext | None]` matches between the type alias, the middleware loop, the worked-example doc, and the integration test.

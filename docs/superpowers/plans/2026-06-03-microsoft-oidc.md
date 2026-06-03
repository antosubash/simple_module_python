# Microsoft (Entra ID) OAuth + DB-settings-driven providers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class `microsoft` OAuth provider and move all OAuth providers off env vars onto the DB-backed settings UI, resolving providers at request time so DB-only credentials actually mount and changes apply without a restart.

**Architecture:** OAuth routes become a single provider-agnostic dispatcher (`/auth/{provider}/{login,callback}`) mounted unconditionally at construction. Each request resolves its provider from a client cache on `app.state.users.oauth_clients`, built in `on_startup` from hydrated DB settings and rebuilt on the `SettingsReloaded` event. The login-button list is derived from that same cache.

**Tech Stack:** Python 3.12, FastAPI, `fastapi-users`, `httpx_oauth` (ships `MicrosoftGraphOAuth2`), pydantic-settings, in-process `EventBus` (pyee), pytest + anyio.

**Spec:** `docs/superpowers/specs/2026-06-03-microsoft-oidc-design.md`

---

## Conventions for every task

- Work from the worktree root: `/home/anto/Repos/simple_module_python/.claude/worktrees/microsoft-oidc`.
- Run the OAuth suite with: `uv run pytest modules/users/tests/test_oauth.py -v`
- A single test: `uv run pytest modules/users/tests/test_oauth.py::test_name -v`
- Before each commit, format the files you touched: `uv run ruff format <files>` (line-length is 100; `make lint` runs `ruff format --check` and will fail on unformatted code).
- Async tests use `@pytest.mark.anyio` and sync tests are plain `def` — match the existing `modules/users/tests/test_oauth.py` style.
- Each task ends green. Tests written first will be red until the implementation step in the same task.

## File map

| File | Responsibility | Tasks |
|------|----------------|-------|
| `modules/users/users/settings.py` | OAuth provider settings (Microsoft added; all OAuth fields DB-backed + grouped) | 1 |
| `modules/users/users/oauth/providers.py` | Build httpx_oauth clients; `microsoft` branch; `build_client_map`; drop `enabled_provider_names` | 2, 4 |
| `modules/users/users/oauth/__init__.py` | Public exports | 2, 4 |
| `modules/users/users/state.py` | `UsersState.oauth_clients` cache field | 3 |
| `modules/users/users/oauth/api.py` | Single request-time OAuth dispatcher | 4 |
| `modules/users/users/module.py` | Unconditional mount; `on_startup` cache build; `register_event_handlers` reload | 4, 5 |
| `modules/users/tests/test_oauth.py` | Unit + integration tests | 1–5 |
| `modules/users/README.md` | Provider setup + migration docs | 6 |

---

## Task 1: Settings — Microsoft fields, all OAuth fields DB-backed + grouped

**Files:**
- Modify: `modules/users/users/settings.py` (the OAuth block, currently lines ~87–100)
- Test: `modules/users/tests/test_oauth.py`

- [ ] **Step 1: Write the failing tests**

Add to `modules/users/tests/test_oauth.py` (after the existing imports / settings-section tests):

```python
def test_microsoft_settings_defaults():
    s = UsersSettings()
    assert s.oauth_microsoft_client_id == ""
    assert s.oauth_microsoft_client_secret == ""
    assert s.oauth_microsoft_tenant == "common"


def test_oauth_fields_carry_group_metadata_for_settings_ui():
    fields = UsersSettings.model_fields
    assert fields["oauth_google_client_id"].json_schema_extra == {"group": "Google OAuth"}
    assert fields["oauth_github_client_id"].json_schema_extra == {"group": "GitHub OAuth"}
    assert fields["oauth_oidc_discovery_url"].json_schema_extra == {"group": "OIDC"}
    assert fields["oauth_microsoft_client_secret"].json_schema_extra == {"group": "Microsoft OAuth"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest modules/users/tests/test_oauth.py::test_microsoft_settings_defaults modules/users/tests/test_oauth.py::test_oauth_fields_carry_group_metadata_for_settings_ui -v`
Expected: FAIL — `oauth_microsoft_*` attributes don't exist / `json_schema_extra` is `None`.

- [ ] **Step 3: Replace the OAuth settings block**

In `modules/users/users/settings.py`, replace the current block (the comment + `oauth_google_*` / `oauth_github_*` / `oauth_oidc_*` fields, lines ~87–100) with:

```python
    # OAuth / OIDC providers — configured via the admin settings UI
    # (/settings/modules → Users). Credentials live in the DB-backed settings
    # store and hydrate after boot; secret fields are masked in the UI (the
    # same treatment the SMTP password gets). Provider changes apply live via
    # the SettingsReloaded event — no restart (see users/module.py).
    oauth_google_client_id: str = Field(default="", json_schema_extra={"group": "Google OAuth"})
    oauth_google_client_secret: str = Field(default="", json_schema_extra={"group": "Google OAuth"})
    oauth_github_client_id: str = Field(default="", json_schema_extra={"group": "GitHub OAuth"})
    oauth_github_client_secret: str = Field(default="", json_schema_extra={"group": "GitHub OAuth"})
    # Generic OIDC — any provider that exposes a discovery URL
    # (Keycloak, Authentik, Auth0, Zitadel, ...).
    oauth_oidc_client_id: str = Field(default="", json_schema_extra={"group": "OIDC"})
    oauth_oidc_client_secret: str = Field(default="", json_schema_extra={"group": "OIDC"})
    oauth_oidc_discovery_url: str = Field(default="", json_schema_extra={"group": "OIDC"})
    oauth_oidc_display_name: str = Field(default="OIDC", json_schema_extra={"group": "OIDC"})
    # Microsoft Entra ID / Microsoft accounts. tenant: "common" (any work/school
    # or personal account), "organizations" (work/school only), or a tenant GUID
    # to restrict sign-in to a single Entra tenant.
    oauth_microsoft_client_id: str = Field(
        default="", json_schema_extra={"group": "Microsoft OAuth"}
    )
    oauth_microsoft_client_secret: str = Field(
        default="", json_schema_extra={"group": "Microsoft OAuth"}
    )
    oauth_microsoft_tenant: str = Field(
        default="common", json_schema_extra={"group": "Microsoft OAuth"}
    )
```

Notes:
- `Field` is already imported (`from pydantic import Field, model_validator`).
- Keep `env_str` imported and untouched — the two token-secret fields still use it (deliberate bootstrap path). Do **not** change `reset_password_token_secret` / `verification_token_secret`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest modules/users/tests/test_oauth.py -v`
Expected: PASS (new tests pass; existing `test_build_clients_google_and_github` and `test_enabled_provider_names_*` still pass — they pass kwargs, not env).

- [ ] **Step 5: Commit**

```bash
git add modules/users/users/settings.py modules/users/tests/test_oauth.py
git commit -m "feat(users): DB-backed, grouped OAuth settings + Microsoft fields"
```

---

## Task 2: providers.py — Microsoft client + `build_client_map`

**Files:**
- Modify: `modules/users/users/oauth/providers.py`
- Modify: `modules/users/users/oauth/__init__.py`
- Test: `modules/users/tests/test_oauth.py`

- [ ] **Step 1: Write the failing tests**

In `modules/users/tests/test_oauth.py`, update the `users.oauth` import to add `build_client_map`:

```python
from users.oauth import build_client_map, build_clients, enabled_provider_names
```

Add these tests in the `build_clients` section:

```python
def test_build_clients_includes_microsoft():
    s = UsersSettings(
        oauth_microsoft_client_id="ms-id",
        oauth_microsoft_client_secret="ms-secret",
    )
    providers = build_clients(s)
    assert [p.name for p in providers] == ["microsoft"]
    assert providers[0].display_name == "Microsoft"
    assert providers[0].client.client_id == "ms-id"


def test_build_clients_skips_microsoft_without_secret():
    s = UsersSettings(oauth_microsoft_client_id="ms-id")  # no secret
    assert [p.name for p in build_clients(s)] == []


@pytest.mark.anyio
async def test_microsoft_authorize_url_carries_tenant():
    s = UsersSettings(
        oauth_microsoft_client_id="ms-id",
        oauth_microsoft_client_secret="ms-secret",
        oauth_microsoft_tenant="my-tenant-guid",
    )
    client = build_client_map(s)["microsoft"].client
    url = await client.get_authorization_url("http://testserver/cb", "state123")
    assert "my-tenant-guid" in url


def test_build_client_map_keys_by_name():
    s = UsersSettings(
        oauth_google_client_id="g-id",
        oauth_google_client_secret="g-secret",
        oauth_microsoft_client_id="ms-id",
        oauth_microsoft_client_secret="ms-secret",
    )
    m = build_client_map(s)
    assert set(m) == {"google", "microsoft"}
    assert m["microsoft"].name == "microsoft"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest modules/users/tests/test_oauth.py -k "microsoft or build_client_map" -v`
Expected: FAIL — `build_client_map` import error / no `microsoft` provider.

- [ ] **Step 3: Add the Microsoft branch + `build_client_map`**

In `modules/users/users/oauth/providers.py`, inside `build_clients`, insert the Microsoft branch **after** the GitHub branch and **before** the OIDC branch:

```python
    if settings.oauth_microsoft_client_id and settings.oauth_microsoft_client_secret:
        from httpx_oauth.clients.microsoft import MicrosoftGraphOAuth2

        out.append(
            OAuthProvider(
                "microsoft",
                "Microsoft",
                MicrosoftGraphOAuth2(
                    settings.oauth_microsoft_client_id,
                    settings.oauth_microsoft_client_secret,
                    tenant=settings.oauth_microsoft_tenant or "common",
                    name="microsoft",
                ),
            )
        )
```

At the end of the file, add:

```python
def build_client_map(settings: UsersSettings) -> dict[str, OAuthProvider]:
    """Configured providers keyed by name for O(1) request-time lookup."""
    return {p.name: p for p in build_clients(settings)}
```

- [ ] **Step 4: Export `build_client_map`**

In `modules/users/users/oauth/__init__.py`, update both lines:

```python
from users.oauth.providers import (
    OAuthProvider,
    build_client_map,
    build_clients,
    enabled_provider_names,
)

__all__ = ["OAuthProvider", "build_client_map", "build_clients", "enabled_provider_names"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest modules/users/tests/test_oauth.py -v`
Expected: PASS (all, including existing).

- [ ] **Step 6: Commit**

```bash
git add modules/users/users/oauth/providers.py modules/users/users/oauth/__init__.py modules/users/tests/test_oauth.py
git commit -m "feat(users): Microsoft OAuth client + build_client_map"
```

---

## Task 3: state.py — `oauth_clients` cache field

**Files:**
- Modify: `modules/users/users/state.py`
- Test: `modules/users/tests/test_oauth.py`

- [ ] **Step 1: Write the failing test**

Add to `modules/users/tests/test_oauth.py`:

```python
def test_users_state_defaults_empty_oauth_clients():
    from users.state import UsersState

    state = UsersState(settings=UsersSettings())
    assert state.oauth_clients == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest modules/users/tests/test_oauth.py::test_users_state_defaults_empty_oauth_clients -v`
Expected: FAIL — `UsersState` has no `oauth_clients`.

- [ ] **Step 3: Add the field**

In `modules/users/users/state.py`:

Add to the `TYPE_CHECKING` block:

```python
    from users.oauth.providers import OAuthProvider
```

Add the field at the end of the `UsersState` dataclass (after `oauth_providers`):

```python
    oauth_clients: dict[str, OAuthProvider] = field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest modules/users/tests/test_oauth.py::test_users_state_defaults_empty_oauth_clients -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/users/users/state.py modules/users/tests/test_oauth.py
git commit -m "feat(users): add oauth_clients cache slot to UsersState"
```

---

## Task 4: Request-time dispatcher + module wiring (lockstep refactor)

This task changes the route shape, `register_oauth_routes`' signature, `module.py`, and removes `enabled_provider_names` — all interdependent, so the implementation edits land together and tests run once at the end.

**Files:**
- Rewrite: `modules/users/users/oauth/api.py`
- Modify: `modules/users/users/module.py` (`register_routes`, `on_startup`)
- Modify: `modules/users/users/oauth/providers.py` (remove `enabled_provider_names`)
- Modify: `modules/users/users/oauth/__init__.py` (drop the export)
- Test: `modules/users/tests/test_oauth.py`

- [ ] **Step 1: Write the failing dispatcher tests**

In `modules/users/tests/test_oauth.py`, add these tests (they import `OAuthProvider` locally; the top-level import is finalized in Step 6):

```python
@pytest.mark.anyio
async def test_oauth_login_redirects_for_configured_provider(users_app, anon_client):
    from httpx_oauth.clients.microsoft import MicrosoftGraphOAuth2
    from users.oauth import OAuthProvider

    users_app.state.users.oauth_clients["microsoft"] = OAuthProvider(
        "microsoft", "Microsoft", MicrosoftGraphOAuth2("ms-id", "ms-secret")
    )
    resp = await anon_client.get("/api/users/auth/microsoft/login", follow_redirects=False)
    assert resp.status_code == 302
    assert "login.microsoftonline.com" in resp.headers["location"]


@pytest.mark.anyio
async def test_oauth_login_404_for_unknown_provider(anon_client):
    resp = await anon_client.get("/api/users/auth/nope/login", follow_redirects=False)
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_oauth_callback_rejects_bad_state(users_app, anon_client):
    from httpx_oauth.clients.microsoft import MicrosoftGraphOAuth2
    from users.oauth import OAuthProvider

    users_app.state.users.oauth_clients["microsoft"] = OAuthProvider(
        "microsoft", "Microsoft", MicrosoftGraphOAuth2("ms-id", "ms-secret")
    )
    resp = await anon_client.get(
        "/api/users/auth/microsoft/callback?code=abc&state=bad", follow_redirects=False
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run to confirm they fail**

Run: `uv run pytest modules/users/tests/test_oauth.py -k "oauth_login or bad_state" -v`
Expected: FAIL — `/auth/{provider}/...` dispatcher doesn't exist yet (per-provider routes only mount when configured).

- [ ] **Step 3: Rewrite `modules/users/users/oauth/api.py`**

Replace the entire file with:

```python
"""OAuth/OIDC login routes — a single provider-agnostic dispatcher.

One pair of routes (``/auth/{provider}/login`` + ``/auth/{provider}/callback``)
serves every provider. The client is resolved per request from
``app.state.users.oauth_clients`` — the cache built in ``UsersModule.on_startup``
from hydrated DB settings and rebuilt on ``SettingsReloaded``. Routes mount
unconditionally at construction (before settings hydrate), so providers
configured through the settings UI work and take effect without a restart.

Why a custom handler rather than ``fastapi_users.get_oauth_router``: the stock
``/callback`` returns 204; Inertia needs the browser to land on a real page, so
``/callback`` returns a 303 redirect to ``login_redirect_url`` with the auth
cookie attached. Find-or-create + email-association go through
``UserManager.oauth_callback``. State CSRF uses Starlette's signed session
cookie.
"""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi_users import exceptions as fu_exceptions
from starlette.responses import RedirectResponse

from users.deps import auth_backend, get_user_manager

if TYPE_CHECKING:
    from users.manager import UserManager
    from users.oauth.providers import OAuthProvider

logger = logging.getLogger(__name__)

_SESSION_STATE_KEY_FMT = "oauth_state:{provider}"
_CALLBACK_ROUTE_NAME = "users_oauth_callback"


def _resolve_provider(request: Request, provider: str) -> OAuthProvider:
    """Return the configured provider by name, or raise 404."""
    found = request.app.state.users.oauth_clients.get(provider)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OAUTH_PROVIDER_NOT_FOUND"
        )
    return found


def register_oauth_routes(api_router: APIRouter) -> None:
    """Mount the provider-agnostic OAuth dispatcher under ``/auth``."""
    router = APIRouter(prefix="/auth", tags=["users-auth"])

    @router.get("/{provider}/login")
    async def begin(request: Request, provider: str) -> RedirectResponse:
        """Generate a state nonce, stash it in the session, redirect to the IdP."""
        provider_obj = _resolve_provider(request, provider)
        state = secrets.token_urlsafe(32)
        request.session[_SESSION_STATE_KEY_FMT.format(provider=provider)] = state
        callback_url = str(request.url_for(_CALLBACK_ROUTE_NAME, provider=provider))
        authorization_url = await provider_obj.client.get_authorization_url(callback_url, state)
        return RedirectResponse(authorization_url, status_code=302)

    @router.get("/{provider}/callback", name=_CALLBACK_ROUTE_NAME)
    async def callback(
        request: Request,
        provider: str,
        code: str | None = None,
        state: str | None = None,
        user_manager: UserManager = Depends(get_user_manager),
        strategy=Depends(auth_backend.get_strategy),
    ) -> RedirectResponse:
        """Verify state, exchange code, find-or-create user, set cookie, redirect."""
        provider_obj = _resolve_provider(request, provider)
        state_key = _SESSION_STATE_KEY_FMT.format(provider=provider)
        expected_state = request.session.pop(state_key, None)
        if not state or not expected_state or not secrets.compare_digest(state, expected_state):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_INVALID_STATE"
            )
        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_MISSING_CODE"
            )

        callback_url = str(request.url_for(_CALLBACK_ROUTE_NAME, provider=provider))
        token = await provider_obj.client.get_access_token(code, callback_url)
        account_id, account_email = await provider_obj.client.get_id_email(token["access_token"])
        if account_email is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_NO_EMAIL")

        try:
            user = await user_manager.oauth_callback(
                provider,
                token["access_token"],
                account_id,
                account_email,
                token.get("expires_at"),
                token.get("refresh_token"),
                request,
                associate_by_email=True,
                is_verified_by_default=True,
            )
        except fu_exceptions.UserAlreadyExists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAUTH_USER_ALREADY_EXISTS",
            ) from None

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="LOGIN_BAD_CREDENTIALS"
            )

        login_response = await auth_backend.login(strategy, user)
        await user_manager.on_after_login(user, request, login_response)

        redirect_url = request.app.state.users.settings.login_redirect_url
        redirect = RedirectResponse(redirect_url, status_code=303)
        for key, value in login_response.headers.items():
            if key.lower() == "set-cookie":
                redirect.raw_headers.append((b"set-cookie", value.encode("latin-1")))
        return redirect

    api_router.include_router(router)
```

- [ ] **Step 4: Update `register_routes` in `modules/users/users/module.py`**

Remove the `from users.settings import UsersSettings` import and the `settings = UsersSettings()` block (current lines ~114–121, including the multi-line comment above it). Change the OAuth mount call (current line ~149) from `register_oauth_routes(api_router, settings)` to:

```python
        register_oauth_routes(api_router)
```

(The `from users.oauth.api import register_oauth_routes` import stays.)

- [ ] **Step 5: Update `on_startup` in `modules/users/users/module.py`**

Change the import (current line ~163) from:

```python
        from users.oauth.providers import enabled_provider_names
```

to:

```python
        from users.oauth.providers import build_client_map
```

Replace the button-list assignment (current line ~178) `state.oauth_providers = enabled_provider_names(s)` with:

```python
        state.oauth_clients = build_client_map(s)
        state.oauth_providers = [
            {"name": p.name, "display_name": p.display_name}
            for p in state.oauth_clients.values()
        ]
```

- [ ] **Step 6: Remove `enabled_provider_names`**

In `modules/users/users/oauth/providers.py`, delete the entire `enabled_provider_names` function (and its docstring).

In `modules/users/users/oauth/__init__.py`, drop the symbol:

```python
from users.oauth.providers import OAuthProvider, build_client_map, build_clients

__all__ = ["OAuthProvider", "build_client_map", "build_clients"]
```

In `modules/users/tests/test_oauth.py`:
- Change the import to `from users.oauth import OAuthProvider, build_client_map, build_clients`.
- Delete the four now-obsolete tests: `test_enabled_provider_names_empty_by_default`, `test_enabled_provider_names_lists_configured_providers`, `test_enabled_provider_names_skips_provider_missing_secret`, `test_enabled_provider_names_oidc_requires_discovery_url`.

- [ ] **Step 7: Run the full OAuth suite**

Run: `uv run pytest modules/users/tests/test_oauth.py -v`
Expected: PASS — dispatcher tests pass, no import errors, existing find-or-create tests still pass.

- [ ] **Step 8: Boot-smoke the app builds (catches wiring errors the unit tests miss)**

Run: `uv run pytest modules/users/tests/test_views.py modules/users/tests/test_api_auth.py -q`
Expected: PASS — confirms `register_routes` + `on_startup` still build a working app.

- [ ] **Step 9: Commit**

```bash
git add modules/users/users/oauth/api.py modules/users/users/module.py modules/users/users/oauth/providers.py modules/users/users/oauth/__init__.py modules/users/tests/test_oauth.py
git commit -m "refactor(users): request-time OAuth dispatcher over hydrated settings"
```

---

## Task 5: Live reload on `SettingsReloaded`

**Files:**
- Modify: `modules/users/users/module.py` (add `register_event_handlers`)
- Test: `modules/users/tests/test_oauth.py`

- [ ] **Step 1: Write the failing tests**

Add to `modules/users/tests/test_oauth.py`:

```python
@pytest.mark.anyio
async def test_settings_reload_adds_provider_to_cache(users_app):
    from settings.contracts.events import SettingsReloaded

    assert users_app.state.users.oauth_clients == {}
    assert users_app.state.users.oauth_providers == []

    users_app.state.users.settings = users_app.state.users.settings.model_copy(
        update={"oauth_microsoft_client_id": "ms-id", "oauth_microsoft_client_secret": "ms-secret"}
    )
    await users_app.state.sm.event_bus.publish(
        SettingsReloaded(package="users", changed=("oauth_microsoft_client_id",))
    )

    assert "microsoft" in users_app.state.users.oauth_clients
    buttons = users_app.state.users.oauth_providers
    assert {"name": "microsoft", "display_name": "Microsoft"} in buttons


@pytest.mark.anyio
async def test_settings_reload_removes_cleared_provider(users_app):
    from settings.contracts.events import SettingsReloaded

    users_app.state.users.settings = users_app.state.users.settings.model_copy(
        update={"oauth_microsoft_client_id": "ms-id", "oauth_microsoft_client_secret": "ms-secret"}
    )
    await users_app.state.sm.event_bus.publish(
        SettingsReloaded(package="users", changed=("oauth_microsoft_client_id",))
    )
    assert "microsoft" in users_app.state.users.oauth_clients

    users_app.state.users.settings = users_app.state.users.settings.model_copy(
        update={"oauth_microsoft_client_id": "", "oauth_microsoft_client_secret": ""}
    )
    await users_app.state.sm.event_bus.publish(
        SettingsReloaded(package="users", changed=("oauth_microsoft_client_id",))
    )
    assert "microsoft" not in users_app.state.users.oauth_clients


@pytest.mark.anyio
async def test_settings_reload_ignores_other_packages(users_app):
    from settings.contracts.events import SettingsReloaded

    sentinel = object()
    users_app.state.users.oauth_clients["microsoft"] = sentinel
    await users_app.state.sm.event_bus.publish(
        SettingsReloaded(package="background_tasks", changed=("broker_url",))
    )
    assert users_app.state.users.oauth_clients["microsoft"] is sentinel
```

- [ ] **Step 2: Run to confirm they fail**

Run: `uv run pytest modules/users/tests/test_oauth.py -k settings_reload -v`
Expected: FAIL — publishing the event has no effect (no subscriber yet); the "adds" and "removes" assertions fail.

- [ ] **Step 3: Add `register_event_handlers` to `UsersModule`**

In `modules/users/users/module.py`, add this method to the `UsersModule` class (place it after `register_settings`). Keep the `EventBus`/`FastAPI` types behind `TYPE_CHECKING` — `FastAPI` is already imported there; add `EventBus` to that block:

```python
    def register_event_handlers(self, bus: EventBus, app: FastAPI | None = None) -> None:
        """Rebuild the OAuth client cache when the users settings reload.

        Routes mount at construction (before DB hydration), so the cache is the
        single source of truth at request time. Rebuilding it here lets an admin
        add/remove a provider via the settings UI without a restart.
        """
        if app is None:
            return

        import importlib

        settings_reloaded = importlib.import_module("settings.contracts.events").SettingsReloaded
        from users.oauth.providers import build_client_map

        async def _rebuild_oauth_clients(event) -> None:
            if event.package != "users":
                return
            state = app.state.users
            state.oauth_clients = build_client_map(state.settings)
            state.oauth_providers = [
                {"name": p.name, "display_name": p.display_name}
                for p in state.oauth_clients.values()
            ]

        bus.subscribe(settings_reloaded, _rebuild_oauth_clients)
```

Add the `EventBus` import to the `TYPE_CHECKING` block at the top of the file:

```python
if TYPE_CHECKING:
    from fastapi import FastAPI
    from simple_module_core.events import EventBus
```

- [ ] **Step 4: Run to confirm they pass**

Run: `uv run pytest modules/users/tests/test_oauth.py -k settings_reload -v`
Expected: PASS

- [ ] **Step 5: Run the full OAuth suite**

Run: `uv run pytest modules/users/tests/test_oauth.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add modules/users/users/module.py modules/users/tests/test_oauth.py
git commit -m "feat(users): hot-reload OAuth providers on SettingsReloaded"
```

---

## Task 6: Docs — README setup + migration note

**Files:**
- Modify: `modules/users/README.md`

- [ ] **Step 1: Add a "Social / Microsoft sign-in" section**

Append to `modules/users/README.md` (before the License line):

```markdown
## Social sign-in (Google, GitHub, Microsoft, OIDC)

OAuth providers are configured in the admin UI at **/settings/modules → Users**
(no environment variables). Each provider activates once its client id **and**
secret are set; the secret is masked in the UI. Changes apply live — no restart.

**Microsoft (Entra ID).** Register an app in the Entra admin center and set the
redirect URI to `<base-url>/api/users/auth/microsoft/callback`. Configure under
the **Microsoft OAuth** group:

- `oauth_microsoft_client_id`, `oauth_microsoft_client_secret`
- `oauth_microsoft_tenant` — `common` (any work/school or personal account,
  the default), `organizations` (work/school only), or your tenant GUID to
  restrict sign-in to one tenant.

Each provider's callback URL is `<base-url>/api/users/auth/<provider>/callback`
(`google`, `github`, `microsoft`, `oidc`).

> **Note:** for Microsoft *guest/external* accounts the identity email comes
> from the Graph `userPrincipalName`, which may not be a plain email
> (e.g. `user_ext.com#EXT#@tenant.onmicrosoft.com`). For tenant members it is
> the user's email.

### Migrating from `SM_USERS_OAUTH_*` env vars

Earlier versions read provider credentials from `SM_USERS_OAUTH_*` environment
variables. These are no longer read at runtime. Migrate existing values into the
settings store once with:

    uv run smpy settings import-from-env
```

- [ ] **Step 2: Verify the doc renders / no broken file-size rule**

Run: `uv run python scripts/check_file_size.py modules/users/README.md || true`
Expected: no error (Markdown isn't capped, but confirm the command is clean).

- [ ] **Step 3: Commit**

```bash
git add modules/users/README.md
git commit -m "docs(users): social sign-in setup + env→settings migration"
```

---

## Task 7: Full verification

- [ ] **Step 1: Run the whole users suite**

Run: `uv run pytest modules/users/tests/ -q`
Expected: PASS (no failures, no import errors).

- [ ] **Step 2: Format, then run lint**

Run: `uv run ruff format modules/users/` then `make lint`
Expected: PASS — Ruff format/lint, `ty`, Biome, `tsc`, and the 300-line cap all clean. (`api.py`, `settings.py`, `module.py` all stay well under 300 lines.)

- [ ] **Step 3: Run module diagnostics**

Run: `make doctor`
Expected: no new errors/warnings for the `users` module — in particular no `SM012` (`register_settings` still sets `app.state.users`) and no `SM019` (users still registers menu items + permissions).

- [ ] **Step 4: Final commit if anything changed**

```bash
git add -A
git commit -m "chore(users): lint/doctor clean for Microsoft OAuth work" || true
```

---

## Self-review notes (author)

- **Spec coverage:** settings (T1), Microsoft client + map (T2), state cache (T3), dispatcher + button derivation + `enabled_provider_names` removal + module wiring (T4), hot-reload (T5), docs + migration + UPN caveat (T6), lint/doctor (T7). All spec sections map to a task.
- **No migration task** — intentional: `OAuthAccount.oauth_name` is a plain string; settings persist in the existing settings store. (Stated in spec "Data / migrations".)
- **Type/name consistency:** `build_client_map`, `OAuthProvider(name, display_name, client)`, route name `users_oauth_callback`, session key `oauth_state:{provider}`, cache attr `app.state.users.oauth_clients`, event `SettingsReloaded(package, changed)`, bus at `app.state.sm.event_bus` — all used identically across tasks.
- **Frontend:** no change required (Login.tsx already maps `oauth_providers`); not a task.
```

# simple_module_auth

Pluggable authentication core for [simple_module](https://github.com/antosubash/simple_module_python) apps. Owns the stable public contracts every other module imports — `UserContext`, the `AuthProvider` protocol, the `PrincipalResolver` chain, and the `get_current_user` / `CurrentUser` dependencies — plus the `AuthMiddleware` that resolves the current principal on every request.

**Heads up:** for most apps you don't install this directly — an auth-provider module (`simple_module_users` for email+password, `simple_module_keycloak` for OIDC) pulls it in and registers itself on `app.state.auth.auth_provider`.

## Install

```bash
pip install simple_module_auth
```

## What it provides

- `UserContext` — the request-scoped principal (`id`, `name`, `email`, `roles`).
- `AuthProvider` protocol — the swappable-backend contract (`resolve_user`, `get_login_url`, `get_logout_url`, `is_bearer_request`); exactly one provider module registers an implementation on `app.state.auth.auth_provider`.
- `PrincipalResolver` chain — async `(Request) -> UserContext | None` callables apps append to `app.state.auth.principal_resolvers` (e.g. PAT/bearer-token or API-key auth), consulted after the session path.
- `AuthMiddleware` — delegates to the provider + resolver chain on every request and populates the request principal.
- `get_current_user` / `CurrentUser` dependency.
- Anonymous-access is declared via the framework's method-aware `register_public_routes` hook (with the `SM_AUTH_PUBLIC_PATHS` host-level escape hatch).

## Usage

```python
from fastapi import APIRouter

from auth.deps import CurrentUser

router = APIRouter()


@router.get("/me")
async def me(user: CurrentUser):
    return {"user_id": user.id, "email": user.email}
```

Routes that need a specific permission use `RequiresPermission` from hosting:

```python
from fastapi import Depends

from simple_module_hosting.permissions import RequiresPermission

from .constants import PERM_PRODUCTS_CREATE


@router.post("/", dependencies=[Depends(RequiresPermission(PERM_PRODUCTS_CREATE))])
async def create_product(): ...
```

`auth.deps.require_permission` is deprecated and will be removed in **0.1.0**
(#698). It retains its legacy any-of semantics, role-based admin bypass and cached
permission check. Migrate to `RequiresPermission(PERM_KEY)`; for several required
permissions, declare a dependency for each. Unlike the legacy helper,
`RequiresPermission` rechecks administrators demoted during the request.

## Depends on

- `simple_module_core`, `simple_module_db`
- `itsdangerous`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

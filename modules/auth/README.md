# simple_module_auth

Session-cookie authentication primitives for [simple_module](https://github.com/antosubash/simple_module_python) apps. Provides the `SessionMiddleware` wiring, login/logout helpers, and login-redirect handling used by the `simple_module_users` module.

**Heads up:** for most apps you don't install this directly — `simple_module_users` pulls it in and builds the email+password auth flow on top of these primitives.

## Install

```bash
pip install simple_module_auth
```

## What it provides

- Starlette `SessionMiddleware` configuration reading `SM_SECRET_KEY` and `SM_SESSION_COOKIE_*` env vars.
- `current_user_id` FastAPI dependency reading the signed session cookie.
- Redirect-to-login helpers for unauthenticated requests on Inertia routes.
- Login-required decorator / dependency for protecting routes without pulling in the heavier `simple_module_users` package.

## Usage

```python
from fastapi import APIRouter, Depends
from simple_module_auth import require_login

router = APIRouter()


@router.get("/me")
async def me(user_id: int = Depends(require_login)):
    return {"user_id": user_id}
```

Routes that need more than just "logged in" (e.g. role/permission checks) should use `simple_module_permissions` instead.

## Depends on

- `simple_module_core`, `simple_module_db`
- `itsdangerous`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

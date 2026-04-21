# simple_module_users

Email+password user management for [simple_module](https://github.com/antosubash/simple_module_python) apps. Replaces Keycloak/Auth0 for the common case: local accounts, admin invites, password reset, optional public signup. Built on `fastapi-users`.

## Install

```bash
pip install simple_module_users
```

Pre-wired into any app scaffolded with `simple-module new`.

## What it provides

- Email + password registration, login, logout, password reset.
- Admin invite flow — admin enters an email, recipient clicks a link, sets a password, is logged in.
- Public signup toggle (`SM_USERS_ALLOW_SIGNUP`, default `false`).
- Bootstrap admin via env vars (`SM_USERS_BOOTSTRAP_EMAIL` + `SM_USERS_BOOTSTRAP_PASSWORD`) — idempotent, only creates if the users table is empty.
- `sm-users create-admin` CLI for ad-hoc admin creation.
- Inertia pages for login/register/invite-accept/admin-invite.
- Console mailer (logs to stdout) or SMTP mailer (`SM_USERS_MAILER=smtp`).

## Usage

CLI:

```bash
uv run sm-users create-admin --email admin@example.com --password 'change-me'
```

Bootstrap-on-boot (`.env`):

```
SM_USERS_BOOTSTRAP_EMAIL=admin@example.com
SM_USERS_BOOTSTRAP_PASSWORD=change-me
```

Program:

```python
from users.deps import CurrentUser    # type: ignore[import-not-found]

@router.get("/profile")
async def profile(user: CurrentUser):
    return {"email": user.email}
```

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`, `simple_module_auth`
- `fastapi-users[sqlalchemy]>=15,<16`, `aiosmtplib`, `cachetools`, `typer`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

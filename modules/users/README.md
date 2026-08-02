# simple_module_users

Email+password user management for [simple_module](https://github.com/antosubash/simple_module_python) apps. Replaces Keycloak/Auth0 for the common case: local accounts, admin invites, password reset, optional public signup. Built on `fastapi-users`.

## Install

```bash
pip install simple_module_users
```

Pre-wired into any app scaffolded with `smpy new`.

## What it provides

- Email + password registration, login, logout, password reset.
- Admin invite flow — admin enters an email, recipient clicks a link, sets a password, is logged in.
- Public signup toggle (`SM_USERS_ALLOW_SIGNUP`, default `false`).
- Bootstrap admin via env vars (`SM_USERS_BOOTSTRAP_EMAIL` + `SM_USERS_BOOTSTRAP_PASSWORD`) — idempotent, only creates if the users table is empty.
- `smpy users create-admin` CLI for ad-hoc admin creation.
- Inertia pages for login/register/invite-accept/admin-invite.
- Console mailer (logs to stdout) or SMTP mailer (`SM_USERS_MAILER=smtp`).

## Usage

CLI:

```bash
uv run smpy users create-admin --email admin@example.com --password 'change-me'
```

Bootstrap-on-boot (`.env`):

```
SM_USERS_BOOTSTRAP_EMAIL=admin@example.com
SM_USERS_BOOTSTRAP_PASSWORD=change-me
```

Program:

```python
from auth.deps import CurrentUser  # type: ignore[import-not-found]


@router.get("/profile")
async def profile(user: CurrentUser):
    return {"email": user.email}
```

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`, `simple_module_settings`, `simple_module_auth`
- `fastapi-users[sqlalchemy,oauth]>=15,<16`, `aiosmtplib`, `cachetools`, `typer`

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

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

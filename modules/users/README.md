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
- Sends verification, reset and invite emails through the framework mail sender (configure the transport in the `mail` module).
- Demo mode — one-click, read-only shared **admin** and **standard user** accounts on the sign-in card, for public showcase instances.

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
from auth.web.deps import CurrentUser


@router.get("/profile")
async def profile(user: CurrentUser):
    return {"email": user.email}
```

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`, `simple_module_settings`, `simple_module_auth`
- `fastapi-users[sqlalchemy,oauth]>=15,<16`, `cachetools`, `typer`

## Demo mode

For hosting a public showcase instance. Set under **/admin/settings/ → Users**:

```
demo_mode        = true
demo_admin_email = demo-admin@example.com
demo_user_email  = demo-user@example.com
demo_read_only   = true    # default — keep it on
```

The sign-in card grows one button per configured account — **Explore as an
administrator** and **Explore as a standard user** — each posting to
`POST /api/users/auth/demo/{role}`. Neither account's password reaches the
browser. Two accounts because the admin surface is what the framework is for
and the end-user app is what you build with it; a visitor can switch between
them without signing out. Blank either email to offer only the other; that
closes its route too, not just its button.

Both accounts are seeded (and reconciled) at boot and on every settings
reload, and while `demo_read_only` is on, `DemoReadOnlyMiddleware` refuses
every unsafe HTTP method from either demo session — everyone else on the
instance is unaffected. A standing banner tells the visitor they are in a demo.

Full detail, including the `demo_read_only = false` warning, is in
[docs/modules/users.md](../../docs/modules/users.md#demo-mode-hosting-a-showcase-instance).

## Social sign-in (Google, GitHub, Microsoft, OIDC)

OAuth providers are configured in the admin UI at **/settings/modules → Users**
(no environment variables). Each provider activates once its client id **and**
secret are set; the secret is masked in the UI. Changes apply live — no restart.

**Microsoft (Entra ID).** Register an app in the Entra admin center and set the
redirect URI to `<base-url>/api/users/auth/microsoft/callback`; it needs the
`openid`, `profile` and `email` delegated permissions (Graph `User.Read` is not
used). Sign-in is OpenID Connect with PKCE and a nonce, and the identity comes
from the validated ID token. Configure under the **Microsoft OAuth** group:

- `oauth_microsoft_client_id`, `oauth_microsoft_client_secret`
- `oauth_microsoft_tenant` — `common` (any work/school or personal account,
  the default), `organizations` (work/school only), `consumers` (personal
  only), or your tenant GUID to restrict sign-in to one tenant.
- `oauth_microsoft_trust_tenant_upn` — off by default. With a tenant GUID,
  a member account's UPN (`upn` claim, else `preferred_username`) counts as a verified
  email, so it links to an invited or verified local account on first
  sign-in. Guests (an `idp` claim naming another issuer, or `#EXT#`) stay unverified; with any other
  tenant value it has no effect.
  It trusts the tenant's admins: whoever can set a member's UPN can sign in
  as the local account with that address.

**Provisioning through SSO with signup closed.** `oauth_signup_providers`
(e.g. `["microsoft"]`) lets those providers create an account on first sign-in
when they proved the email, while local registration keeps following
`allow_signup`. `oauth_signup_default_role` is the role those accounts get,
with signup open too (never the self-signup `user` role); blank (the default)
means none until an admin grants one, and `admin` is refused.

**Trusted email domains.** `oauth_trusted_email_domains` (e.g.
`{"microsoft": ["iiasa.ac.at"]}`) makes addresses on the listed domains count
as verified for that provider: `microsoft` (a member of a pinned tenant GUID)
and `oidc` only. `oauth_sync_profile` updates `full_name` from the IdP on every
sign-in; each link stores the IdP's subject, username and last sign-in, shown
on the admin Edit user page.

Each provider's callback URL is `<base-url>/api/users/auth/<provider>/callback`
(`google`, `github`, `microsoft`, `oidc`).

> **Note:** the Microsoft identity email is the ID token's optional `upn`
> claim when the app registration adds it, else `preferred_username`: the UPN
> for tenant members, the home address for a guest. A pinned tenant GUID also
> requires the token's `tid` to match it.

### Migrating from `SM_USERS_OAUTH_*` env vars

Earlier versions read provider credentials from `SM_USERS_OAUTH_*` environment
variables. These are no longer read at runtime. Migrate existing values into the
settings store once with:

    uv run smpy settings import-from-env

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

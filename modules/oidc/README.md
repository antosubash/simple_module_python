# simple_module_oidc

Generic **OpenID Connect** authentication provider for simple_module — with
**native Microsoft Entra ID (Azure AD)** support, plus Auth0, Okta, Zitadel,
Authentik, Keycloak, and any OIDC-compliant identity provider.

The module is configured from a provider's OIDC **discovery document**
(`.well-known/openid-configuration`), so endpoints (authorize / token / JWKS /
logout) and the issuer are resolved automatically — no per-provider URL
templating. Provider differences (claim names, scopes) are config; **presets**
fill those in for you.

It auto-registers as the application's auth provider. Browser users are
redirected to the IdP's hosted login; mobile/API clients send a bearer token
which is validated against the provider's JWKS.

## Install

Add to your app's `pyproject.toml` dependencies instead of another auth provider
(e.g. `simple_module_users` / `simple_module_keycloak` — only one auth provider
can be active):

```toml
dependencies = [
    "simple_module_oidc==0.0.17",
]
```

Run `uv sync --all-packages` to install.

## Usage

Pick a provider preset and supply its credentials via environment variables (or
configure them through the settings admin UI after first boot). The module then
auto-registers as the application's auth provider — see the preset sections below.

## Native Microsoft Entra ID

Set the `entra` preset and your single-tenant registration details:

```bash
SM_OIDC_PROVIDER=entra
SM_OIDC_TENANT_ID=<your-tenant-guid>     # or a verified domain
SM_OIDC_CLIENT_ID=<app-registration-client-id>
SM_OIDC_CLIENT_SECRET=<client-secret>
```

In the Entra app registration, add the redirect URI:

```
https://<your-host>/api/oidc/auth/callback
```

The `entra` preset derives the discovery URL
(`https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration`),
validates the **id_token**, keys the user cache on the stable **`oid`** claim, and
maps Entra **app roles** (the `roles` claim) to framework permissions via
`role_mapping` (default: `admin` and `user` map 1:1). Assign app roles in
*Entra → App registrations → App roles* and *Enterprise applications → Users and groups*.

## Any other OIDC provider

Use the `generic` preset with an explicit discovery URL:

```bash
SM_OIDC_PROVIDER=generic
SM_OIDC_DISCOVERY_URL=https://<issuer>/.well-known/openid-configuration
SM_OIDC_CLIENT_ID=<client-id>
SM_OIDC_CLIENT_SECRET=<client-secret>
```

## Configuration reference

| Env var | Default | Notes |
|---|---|---|
| `SM_OIDC_PROVIDER` | `generic` | Preset name (`entra`, `generic`). |
| `SM_OIDC_DISCOVERY_URL` | — | Explicit discovery URL; wins over the preset. |
| `SM_OIDC_TENANT_ID` | — | Used by templated presets (Entra) to derive the discovery URL. |
| `SM_OIDC_CLIENT_ID` | — | OAuth client id. |
| `SM_OIDC_CLIENT_SECRET` | — | OAuth client secret. |
| `SM_OIDC_AUDIENCE` | `client_id` | JWT audience to validate against. |
| `SM_OIDC_SCOPE` | preset | OAuth scope string. |
| `SM_OIDC_UID_CLAIM` | preset (`oid` for Entra, else `sub`) | Stable subject claim. |
| `SM_OIDC_USERNAME_CLAIM` | `preferred_username` | Display-name source. |
| `SM_OIDC_EMAIL_CLAIM` | `email` | Email claim. |
| `SM_OIDC_NAME_CLAIM` | `name` | Fallback display name. |
| `SM_OIDC_ROLES_CLAIM_PATH` | preset (`roles` for Entra) | Dotted path to a roles list (e.g. `realm_access.roles`). |

`login_redirect_url`, `jwks_cache_ttl_seconds`, and `role_mapping` are configurable
via the settings admin UI after first boot.

## Activation

Add `simple_module_oidc` to the host's `pyproject.toml` dependencies and
`[tool.uv.sources]`, remove the competing provider, then `uv sync --all-packages`.
Alternatively scope active modules with `SM_MODULES_ENABLED`.

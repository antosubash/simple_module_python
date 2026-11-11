# Development discovery override and test fixtures for Microsoft sign-in (#879)

## Goal & scope

Since #876 the Microsoft provider is OIDC, but its endpoints are fixed to
`login.microsoftonline.com`, so nobody can click through Microsoft sign-in
locally or in CI without a real Entra tenant. Add a development-only discovery
override, a local Keycloak recipe that emits Entra-shaped claims, and reusable
test helpers for signed ID tokens.

Out of scope: production use of another IdP through the Microsoft provider
(the generic `oidc` provider is for that).

## Approach

- `oauth_microsoft_discovery_url: str = ""`. Honoured **only** when
  `SM_ENVIRONMENT` is development or testing; otherwise ignored, with a
  `users.oauth.microsoft_discovery_ignored` warning (not a boot failure, so an
  admin edit cannot take the site down). Blank keeps today's fixed Entra
  endpoints.
- With an override, `MicrosoftOidc` reads `authorization_endpoint`,
  `token_endpoint`, `jwks_uri` and `issuer` from the discovery document,
  fetched asynchronously on first use and cached (no fetch at boot or settings
  reload), validated with the `oidc` module's rules (HTTPS outside
  development, concrete issuer). The ID token's issuer must then equal the
  document's issuer exactly; the `tid` rules stay (a GUID tenant still requires
  a matching `tid`, so the Keycloak realm emits one).
- Test helpers in `simple_module_test` (framework, so no `users` import):
  `OidcTestIssuer` with an RSA key, `jwks()`, `discovery(base_url)` and
  `sign(claims)`, plus a `oidc_test_issuer` fixture. The users module's own
  helper moves onto it.
- Recipe: `docs/modules/users.md` § "Microsoft sign-in without Entra" and a
  realm export `docs/examples/keycloak-entra-realm.json` with protocol mappers
  for `oid`, `tid`, `preferred_username`, `email`, `name`.

Rejected: a bundled fake IdP server in `simple_module_test` (more code to keep
than a realm file plus in-process fixtures); refusing boot in production
(an admin settings edit would then be able to stop the site).

## Testing

- Settings: override honoured in development/testing, ignored with a warning
  in production.
- Flow: with the override and `pytest-httpx` serving discovery, JWKS and the
  token endpoint from `OidcTestIssuer`, a full `/login` → `/callback` round trip
  signs in; a token whose issuer differs from the document's is refused.
- Manual: the Keycloak recipe against `make dev` (documented, run once here).

## Risks

- Keycloak's `tid`/`oid` must be GUID-shaped; the realm sets them as hardcoded
  or user-attribute mappers with GUID values.

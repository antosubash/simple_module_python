# Plan: Microsoft dev discovery override + test issuer (#879)

Design: `docs/superpowers/specs/2026-11-11-microsoft-dev-idp-design.md`. Sequential.

1. `simple_module_test.oidc_issuer`: `OidcTestIssuer` + `oidc_test_issuer` fixture; deps `PyJWT[crypto]`,
   `cryptography`; tests in `framework/testing/tests/test_testing_oidc_issuer.py`.
2. `users/oauth/microsoft_dev.py` `MicrosoftDevOidc` (lazy async discovery, document issuer);
   `oauth_microsoft_discovery_url` + `microsoft_discovery_url()` (dev/testing only, warning otherwise);
   `build_clients` picks it. Tests: `tests/oauth/devidp/` full round trip via `httpx_mock`.
3. `docs/examples/keycloak-entra-realm.json`; docs (users.md, README, testing/fixtures.md), CHANGELOG;
   manual run against the shared dev Keycloak.

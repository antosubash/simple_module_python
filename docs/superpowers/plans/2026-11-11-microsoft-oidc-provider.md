# Plan: Microsoft sign-in over OIDC (#876)

Design: `docs/superpowers/specs/2026-11-11-microsoft-oidc-provider-design.md`. Sequential.

1. `users/oauth/microsoft.py`: `MicrosoftOidc` (Graph client subclass on v2.0 endpoints,
   scopes `openid profile email`), ID-token validation with per-`tid` `JWKSCache`,
   tenant acceptance, `graph_account_id`, trust rule. Tests:
   `tests/oauth/providers/test_users_oauth_microsoft_id_token.py` with a local RSA key.
2. `OAuthProvider`: `uses_pkce`, `authorization_url`, `exchange_code`,
   `get_identity(token, login)`; `build_clients` builds `MicrosoftOidc` lazily.
3. `users/oauth/api.py`: per-login verifier + nonce in the session, spent with the state;
   missing secrets refused. Tests: `tests/oauth/flow/test_users_oauth_microsoft_pkce.py`;
   existing Microsoft flow tests move to the signed-token helper
   (`tests/_users_microsoft_support.py`).
4. Docs + CHANGELOG (behaviour change). 5. `make lint`, users tests; suites in `/vf`.

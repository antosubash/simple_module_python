"""Keycloak module constants."""

from __future__ import annotations

# Anonymous-allowed prefixes, registered in ``KeycloakModule.register_public_routes``.
PUBLIC_PATH_PREFIXES = (
    "/keycloak/login",
    "/keycloak/logout",
    # Where the end-session redirect lands: there is no session left to check,
    # and bouncing it to /keycloak/login would sign the visitor straight back in.
    "/keycloak/logged-out",
    "/api/keycloak/auth/",
)

SESSION_REFRESH_TOKEN_KEY = "keycloak_refresh_token"
SESSION_REFRESH_RETRY_AT_KEY = "keycloak_refresh_retry_at"
SESSION_ID_TOKEN_KEY = "keycloak_id_token"
SESSION_USER_KEY = "user_ctx"
SESSION_STATE_KEY = "keycloak_oidc_state"
SESSION_NONCE_KEY = "keycloak_oidc_nonce"
SESSION_VERIFIER_KEY = "keycloak_oidc_verifier"

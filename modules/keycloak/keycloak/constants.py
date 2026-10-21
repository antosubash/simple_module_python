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

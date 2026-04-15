"""Keycloak OAuth2/OIDC integration using authlib."""

from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth

# Global OAuth instance — configured at app startup
oauth = OAuth()


def configure_oauth(
    keycloak_url: str,
    realm: str,
    client_id: str,
    client_secret: str,
    *,
    insecure_transport: bool = False,
) -> None:
    """Register the Keycloak OIDC provider.

    When ``insecure_transport`` is True (dev only), allow OAuth callbacks over
    plain HTTP. Authlib otherwise rejects HTTP callback URLs with
    ``invalid_request: HTTPS required``. Production must always use HTTPS.
    """
    if insecure_transport:
        # Authlib reads this env var at request time to decide whether to allow
        # http:// callback URLs. Setting it here keeps the dev workflow free of
        # extra environment plumbing.
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
        os.environ.setdefault("AUTHLIB_INSECURE_TRANSPORT", "1")

    server_metadata_url = f"{keycloak_url}/realms/{realm}/.well-known/openid-configuration"
    oauth.register(
        name="keycloak",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=server_metadata_url,
        client_kwargs={"scope": "openid profile email roles"},
    )

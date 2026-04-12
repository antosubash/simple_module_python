"""Keycloak OAuth2/OIDC integration using authlib."""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

# Global OAuth instance — configured at app startup
oauth = OAuth()


def configure_oauth(
    keycloak_url: str,
    realm: str,
    client_id: str,
    client_secret: str,
) -> None:
    """Register the Keycloak OIDC provider."""
    server_metadata_url = (
        f"{keycloak_url}/realms/{realm}/.well-known/openid-configuration"
    )
    oauth.register(
        name="keycloak",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=server_metadata_url,
        client_kwargs={"scope": "openid profile email"},
    )

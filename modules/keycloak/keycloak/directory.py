"""User directory over the provider's unchanged cache table."""

from auth.oidc_common.directory import CacheDirectory

from keycloak.models import KeycloakUserCache


class KeycloakDirectory(CacheDirectory):
    def __init__(self) -> None:
        super().__init__(KeycloakUserCache)

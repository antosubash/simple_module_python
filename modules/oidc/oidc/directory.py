"""User directory over the provider's unchanged cache table."""

from auth.oidc_common.directory import CacheDirectory

from oidc.models import OidcUserCache


class OidcDirectory(CacheDirectory):
    def __init__(self) -> None:
        super().__init__(OidcUserCache)

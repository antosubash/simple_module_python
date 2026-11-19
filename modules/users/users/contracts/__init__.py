"""Public APIs for modules that depend on Users."""

from users.oauth.providers import OAuthProvider
from users.oauth.registry import OAuthProviderFactory, register_oauth_provider

__all__ = ["OAuthProvider", "OAuthProviderFactory", "register_oauth_provider"]

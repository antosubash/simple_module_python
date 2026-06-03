"""OAuth feature — public surface re-exported for backward compatibility."""

from users.oauth.providers import OAuthProvider, build_client_map, build_clients

__all__ = ["OAuthProvider", "build_client_map", "build_clients"]

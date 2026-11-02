"""Initialize one coherent discovery/client/JWKS configuration per process."""

import logging

from oidc.client import OIDCClient
from oidc.discovery import fetch_metadata
from oidc.jwks import JWKSCache

logger = logging.getLogger(__name__)
_DISCOVERY_SUFFIX = "/.well-known/openid-configuration"


async def initialize(app) -> bool:
    state = app.state.oidc
    development = app.state.sm.settings.environment == "development"
    async with state.initialization_lock:
        if state.client is not None:
            return True
        s = state.settings
        try:
            if not s.discovery_url or not s.client_id:
                raise ValueError("OIDC discovery URL and client ID are required")
            if _DISCOVERY_SUFFIX not in s.discovery_url:
                raise ValueError("OIDC discovery URL must identify its issuer")
            # OIDC discovery uses either issuer + suffix or suffix + issuer path.
            prefix, suffix = s.discovery_url.split(_DISCOVERY_SUFFIX, 1)
            expected_issuer = prefix + suffix
            metadata = await fetch_metadata(
                s.discovery_url, expected_issuer=expected_issuer, development=development
            )
            cache = JWKSCache(
                metadata.jwks_uri,
                ttl_seconds=s.jwks_cache_ttl_seconds,
                issuer=metadata.issuer,
                audience=s.client_id,
            )
            client = OIDCClient(
                authorization_endpoint=metadata.authorization_endpoint,
                token_endpoint=metadata.token_endpoint,
                end_session_endpoint=metadata.end_session_endpoint,
                client_id=s.client_id,
                client_secret=s.client_secret,
            )
        except Exception as exc:
            if not development:
                raise RuntimeError("OIDC discovery failed; authentication unavailable") from exc
            logger.warning("OIDC discovery unavailable; login will retry")
            return False
        state.metadata, state.jwks_cache, state.client = metadata, cache, client
        app.state.auth.auth_provider.jwks_cache = cache
        return True

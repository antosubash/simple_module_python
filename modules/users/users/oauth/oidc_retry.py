"""Request-driven recovery after generic OIDC discovery fails at boot."""

from __future__ import annotations

import asyncio
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx_oauth.clients.openid import OpenID

    from users.core.settings import UsersSettings


class OidcDiscoveryUnavailableError(Exception):
    """Configured SSO is temporarily unavailable, rather than disabled."""


class OidcDiscovery:
    """Keep one retry schedule and successful client per settings snapshot."""

    def __init__(self, settings: UsersSettings):
        from httpx_oauth.clients.openid import OpenID

        self._build = partial(
            OpenID,
            settings.oauth_oidc_client_id,
            settings.oauth_oidc_client_secret,
            settings.oauth_oidc_discovery_url,
            name="oidc",
        )
        self._clock = monotonic
        self._next_attempt = self._clock() + 30
        self._delay = 60
        self._attempt: asyncio.Task[OpenID] | None = None
        self._client: OpenID | None = None

    async def resolve(self) -> OpenID:
        if self._client is not None:
            return self._client
        if self._attempt is None:
            if self._clock() < self._next_attempt:
                raise OidcDiscoveryUnavailableError
            self._attempt = asyncio.create_task(self._discover())
        # A disconnected caller must not discard recovery or release the single attempt.
        return await asyncio.shield(self._attempt)

    async def _discover(self) -> OpenID:
        from httpx_oauth.clients.openid import OpenIDConfigurationError

        try:
            # OpenID performs synchronous HTTP in its constructor; keep it off the event loop.
            self._client = await asyncio.to_thread(self._build)
            return self._client
        except (OpenIDConfigurationError, ValueError, KeyError, TypeError, IndexError):
            self._next_attempt = self._clock() + self._delay
            self._delay = min(self._delay * 2, 600)
            raise OidcDiscoveryUnavailableError from None
        finally:
            self._attempt = None

"""Request-driven recovery after generic OIDC discovery fails at boot."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
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

    def __init__(self, settings: UsersSettings, *, clock: Callable[[], float] | None = None):
        from httpx_oauth.clients.openid import OpenID

        self._build = partial(
            OpenID,
            settings.oauth_oidc_client_id,
            settings.oauth_oidc_client_secret,
            settings.oauth_oidc_discovery_url,
            name="oidc",
        )
        self._clock = clock or monotonic
        self._next_attempt = self._clock() + 30
        self._delay = 60
        self._lock = asyncio.Lock()
        self._client: OpenID | None = None

    async def resolve(self) -> OpenID:
        from httpx_oauth.clients.openid import OpenIDConfigurationError

        async with self._lock:
            if self._client is not None:
                return self._client
            if self._clock() < self._next_attempt:
                raise OidcDiscoveryUnavailableError
            # Cancellation releases the lock while the discovery thread may still be running.
            self._next_attempt = self._clock() + self._delay
            # OpenID performs synchronous HTTP in its constructor; keep it off the event loop.
            try:
                self._client = await asyncio.to_thread(self._build)
            except OpenIDConfigurationError:
                self._next_attempt = self._clock() + self._delay
                self._delay = min(self._delay * 2, 600)
                raise OidcDiscoveryUnavailableError from None
            return self._client

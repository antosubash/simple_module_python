"""Module-scoped state container for the oidc module."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from oidc.core.settings import OidcSettings
    from oidc.identity.client import OIDCClient
    from oidc.identity.discovery import OidcMetadata
    from oidc.identity.jwks import JWKSCache


@dataclass
class OidcState:
    """OIDC-module singletons. Single slot at ``app.state.oidc``."""

    settings: OidcSettings
    metadata: OidcMetadata | None = None
    jwks_cache: JWKSCache | None = None
    client: OIDCClient | None = None

    initialization_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

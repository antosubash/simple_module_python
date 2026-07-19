"""Module-scoped state container for the oidc module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from oidc.client import OIDCClient
    from oidc.discovery import OidcMetadata
    from oidc.jwks import JWKSCache
    from oidc.settings import OidcSettings


@dataclass
class OidcState:
    """OIDC-module singletons. Single slot at ``app.state.oidc``."""

    settings: OidcSettings
    metadata: OidcMetadata | None = None
    jwks_cache: JWKSCache | None = None
    client: OIDCClient | None = None

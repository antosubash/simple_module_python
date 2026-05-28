"""Module-scoped state container for the keycloak module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from keycloak.jwks import JWKSCache
    from keycloak.settings import KeycloakSettings


@dataclass
class KeycloakState:
    """Keycloak-module singletons. Single slot at ``app.state.keycloak``."""

    settings: KeycloakSettings
    jwks_cache: JWKSCache | None = None

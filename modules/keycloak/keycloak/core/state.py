"""Module-scoped state container for the keycloak module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from keycloak.core.settings import KeycloakSettings
    from keycloak.identity.jwks import JWKSCache


@dataclass
class KeycloakState:
    """Keycloak-module singletons. Single slot at ``app.state.keycloak``."""

    settings: KeycloakSettings
    jwks_cache: JWKSCache | None = None

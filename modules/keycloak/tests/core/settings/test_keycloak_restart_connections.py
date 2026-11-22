"""Restart metadata and normalized startup URLs (#1076)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from keycloak.core.settings import KeycloakSettings
from keycloak.module import KeycloakModule


@pytest.mark.parametrize(
    "name", ["server_url", "realm", "client_id", "client_secret", "jwks_cache_ttl_seconds"]
)
def test_connection_settings_require_restart(name):
    assert KeycloakSettings.model_fields[name].json_schema_extra == {"requires_restart": True}


async def test_startup_strips_server_trailing_slashes(monkeypatch):
    cache = MagicMock()
    monkeypatch.setattr("keycloak.identity.jwks.JWKSCache", cache)
    state = SimpleNamespace(
        settings=KeycloakSettings(
            server_url="https://sso.test///", realm="test", client_id="client"
        )
    )
    app = SimpleNamespace(
        state=SimpleNamespace(keycloak=state, auth=SimpleNamespace(auth_provider=SimpleNamespace()))
    )
    await KeycloakModule().on_startup(app)
    assert cache.call_args.kwargs["issuer"] == "https://sso.test/realms/test"
    assert (
        cache.call_args.kwargs["jwks_url"]
        == "https://sso.test/realms/test/protocol/openid-connect/certs"
    )

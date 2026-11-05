"""Accepted discovery endpoints retain their policy/tenant query at authorization."""

from urllib.parse import parse_qs, urlsplit

import pytest
from oidc.identity.client import OIDCClient
from oidc.identity.discovery import OidcMetadata


@pytest.mark.parametrize("query", ["", "?tenant=alpha", "?tenant=alpha&policy=a%2Bb"])
def test_discovered_authorization_query_is_preserved(query):
    metadata = OidcMetadata.from_document(
        {
            "issuer": "https://issuer.example",
            "authorization_endpoint": f"https://issuer.example/authorize{query}",
            "token_endpoint": "https://issuer.example/token",
            "jwks_uri": "https://issuer.example/keys",
        },
        expected_issuer="https://issuer.example",
    )
    client = OIDCClient(
        authorization_endpoint=metadata.authorization_endpoint,
        token_endpoint=metadata.token_endpoint,
        end_session_endpoint="",
        client_id="application-id",
        client_secret="secret",
    )
    url, state = client.build_authorization_url(
        "https://app.example/callback",
        "nonce",
        code_verifier="v" * 64,
    )
    params = parse_qs(urlsplit(url).query)
    assert params["client_id"] == ["application-id"]
    assert params["state"] == [state]
    assert params["nonce"] == ["nonce"]
    assert params["code_challenge_method"] == ["S256"]
    if query:
        assert params["tenant"] == ["alpha"]
    if "policy" in query:
        assert params["policy"] == ["a+b"]

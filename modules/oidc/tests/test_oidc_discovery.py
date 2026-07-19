"""Tests for OIDC discovery document parsing and fetching."""

from __future__ import annotations

import pytest
from oidc.discovery import OidcMetadata, fetch_metadata

_ENTRA_DOC = {
    "issuer": "https://login.microsoftonline.com/tid/v2.0",
    "authorization_endpoint": "https://login.microsoftonline.com/tid/oauth2/v2.0/authorize",
    "token_endpoint": "https://login.microsoftonline.com/tid/oauth2/v2.0/token",
    "jwks_uri": "https://login.microsoftonline.com/tid/discovery/v2.0/keys",
    "end_session_endpoint": "https://login.microsoftonline.com/tid/oauth2/v2.0/logout",
}


def test_from_document_parses_endpoints():
    meta = OidcMetadata.from_document(_ENTRA_DOC)
    assert meta.issuer == "https://login.microsoftonline.com/tid/v2.0"
    assert meta.authorization_endpoint.endswith("/authorize")
    assert meta.token_endpoint.endswith("/token")
    assert meta.jwks_uri.endswith("/keys")
    assert meta.end_session_endpoint.endswith("/logout")


def test_from_document_end_session_optional():
    doc = {k: v for k, v in _ENTRA_DOC.items() if k != "end_session_endpoint"}
    meta = OidcMetadata.from_document(doc)
    assert meta.end_session_endpoint == ""


def test_from_document_requires_core_fields():
    doc = {k: v for k, v in _ENTRA_DOC.items() if k != "jwks_uri"}
    with pytest.raises(ValueError, match="jwks_uri"):
        OidcMetadata.from_document(doc)


async def test_fetch_metadata(httpx_mock):
    url = "https://issuer/.well-known/openid-configuration"
    httpx_mock.add_response(url=url, json=_ENTRA_DOC)
    meta = await fetch_metadata(url)
    assert meta.token_endpoint == _ENTRA_DOC["token_endpoint"]

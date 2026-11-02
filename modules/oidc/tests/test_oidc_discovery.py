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


@pytest.mark.parametrize(
    "value",
    [
        42,
        [],
        "http://idp/keys",
        "javascript:alert(1)",
        "https://u:p@idp/keys",
        "https://idp/keys#frag",
    ],
)
def test_metadata_rejects_invalid_endpoint(value):
    with pytest.raises(ValueError):
        OidcMetadata.from_document({**_ENTRA_DOC, "jwks_uri": value})


def test_metadata_checks_expected_issuer():
    with pytest.raises(ValueError, match="issuer"):
        OidcMetadata.from_document(_ENTRA_DOC, expected_issuer="https://other")


def test_metadata_issuer_tolerates_one_trailing_slash():
    # Auth0 publishes "https://tenant.auth0.com/"; the discovery URL has no slash.
    doc = {**_ENTRA_DOC, "issuer": "https://tenant.example.com/"}
    metadata = OidcMetadata.from_document(doc, expected_issuer="https://tenant.example.com")
    assert metadata.issuer == "https://tenant.example.com/"


def test_metadata_allows_local_http_only_in_development():
    doc = {k: "http://localhost/" + k for k in _ENTRA_DOC}
    assert OidcMetadata.from_document(doc, development=True).jwks_uri.startswith("http:")
    with pytest.raises(ValueError):
        OidcMetadata.from_document(doc)

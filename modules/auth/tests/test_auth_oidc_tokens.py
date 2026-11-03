"""Shared sealing keeps both providers' existing ciphertext formats (#741)."""

import base64
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from keycloak import tokens as keycloak_tokens
from oidc import tokens as oidc_tokens


@pytest.fixture(params=[("keycloak", keycloak_tokens), ("oidc", oidc_tokens)])
def sealing(request):
    name, tokens = request.param
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(settings=SimpleNamespace(secret_key="existing-secret"))
        )
    )
    return name, tokens, app


def test_old_refresh_ciphertext_still_decrypts(sealing):
    name, tokens, app = sealing
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=f"{name}-refresh-token".encode()
    ).derive(b"existing-secret")
    old_ciphertext = Fernet(base64.urlsafe_b64encode(key)).encrypt(b"old-refresh").decode()
    assert tokens.open_refresh_token(app, old_ciphertext) == "old-refresh"


def test_cookie_size_cap_keeps_principal_and_deadline(sealing):
    name, tokens, app = sealing
    session = {"user_ctx": {"id": "user"}, "expires_at": 2000}
    assert tokens.store_refresh_token(app, session, "small")
    assert tokens.open_refresh_token(app, session[f"{name}_refresh_token"]) == "small"
    assert not tokens.store_refresh_token(app, session, "r" * 3000)
    assert session == {"user_ctx": {"id": "user"}, "expires_at": 2000}


def test_tokens_remain_provider_scoped(sealing):
    name, tokens, app = sealing
    other = oidc_tokens if name == "keycloak" else keycloak_tokens
    sealed = tokens.seal_refresh_token(app, "refresh")
    assert other.open_refresh_token(app, sealed) is None
    assert tokens.open_refresh_token(app, sealed[:-5] + "bad") is None

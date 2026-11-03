"""Helpers both OIDC providers build on (#741)."""

import base64
import hashlib
import logging
from types import SimpleNamespace

from auth.oidc_common.session import pkce_challenge
from auth.oidc_common.tenant import trusted_tenant, without_tenant_roles
from auth.oidc_common.tokens import provider_tokens


def test_pkce_challenge_is_s256_unpadded():
    expected = base64.urlsafe_b64encode(hashlib.sha256(b"verifier").digest()).rstrip(b"=")
    assert pkce_challenge("verifier") == expected.decode()


def test_trusted_tenant_requires_trust_and_valid_id(caplog):
    assert trusted_tenant("acme", trust_claim=False) is None
    assert trusted_tenant(None, trust_claim=True) is None
    assert trusted_tenant("acme", trust_claim=True) == "acme"
    with caplog.at_level(logging.WARNING):
        assert trusted_tenant("bad id!", trust_claim=True) is None
    assert "malformed tenant_id" in caplog.text


def test_without_tenant_roles_warns_once_with_provider_label(caplog):
    warned: set[str] = set()
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            kept = without_tenant_roles(["admin", "tenant:owner"], warned=warned, provider="Foo")
    assert kept == ["admin"]
    assert caplog.text.count("Foo role_mapping produced tenant role") == 1


def test_provider_tokens_scope_by_info_and_key():
    app = SimpleNamespace(
        state=SimpleNamespace(sm=SimpleNamespace(settings=SimpleNamespace(secret_key="k")))
    )
    a = provider_tokens(info=b"a", session_key="ka")
    b = provider_tokens(info=b"b", session_key="kb")
    session: dict = {}
    assert a.store_refresh_token(app, session, "tok") is True
    assert "ka" in session
    assert a.open_refresh_token(app, session["ka"]) == "tok"
    assert b.open_refresh_token(app, session["ka"]) is None

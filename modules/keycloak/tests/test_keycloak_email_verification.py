"""Only an explicit verified-email claim can authorize invitation acceptance."""

import pytest
from auth.contracts.schemas import UserContext
from keycloak.provider import KeycloakAuthProvider


@pytest.mark.parametrize("claim", [True, False, None, "true", "false", 1])
def test_email_verification_survives_keycloak_session(claim):
    claims = {"email": "bob@corp.com"}
    if claim is not None:
        claims["email_verified"] = claim
    ctx = KeycloakAuthProvider()._claims_to_user_context(claims, cache_id="bob")
    assert ctx.email_verified is (claim is True)
    restored = UserContext.from_session_dict(ctx.to_session_dict())
    assert restored.email_verified is (claim is True)


def test_legacy_session_does_not_assert_verified_email():
    ctx = UserContext.from_session_dict({"id": "bob", "email": "bob@corp.com", "name": "Bob"})
    assert ctx.email_verified is False

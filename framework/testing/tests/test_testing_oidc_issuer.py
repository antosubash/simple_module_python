"""``OidcTestIssuer`` issues tokens its own JWKS verifies (#879)."""

import jwt
from jwt.algorithms import RSAAlgorithm
from simple_module_test import OidcTestIssuer


def test_signed_tokens_verify_against_the_published_jwks(oidc_test_issuer):
    token = oidc_test_issuer.sign({"aud": "client", "sub": "user-1", "nonce": "n"})
    key = RSAAlgorithm.from_jwk(oidc_test_issuer.jwks()["keys"][0])
    claims = jwt.decode(
        token, key, algorithms=["RS256"], audience="client", issuer=oidc_test_issuer.issuer
    )
    assert (claims["sub"], claims["nonce"]) == ("user-1", "n")
    assert jwt.get_unverified_header(token)["kid"] == oidc_test_issuer.kid


def test_discovery_points_at_the_issuer_endpoints():
    issuer = OidcTestIssuer("https://idp.test/tenant/v2.0/")
    doc = issuer.discovery()
    assert doc["issuer"] == "https://idp.test/tenant/v2.0"
    assert doc["jwks_uri"] == issuer.jwks_url
    assert issuer.discovery_url.endswith("/.well-known/openid-configuration")


def test_none_drops_a_claim(oidc_test_issuer):
    token = oidc_test_issuer.sign({"sub": "x", "exp": None})
    assert "exp" not in jwt.decode(token, options={"verify_signature": False})

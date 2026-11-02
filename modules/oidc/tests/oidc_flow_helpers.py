"""Real signing material for OIDC integration tests."""

import json
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

_KID = "test-key-1"
_ISSUER = "https://login.microsoftonline.com/test-tenant/v2.0"
_AUDIENCE = "my-app"
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _sign_id_token(*, nonce: str, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "exp": now + 3600,
        "iat": now,
        "oid": "entra-oid-123",
        "sub": "pairwise-123",
        "email": "alice@example.com",
        "preferred_username": "alice",
        "tid": "test-tenant",
        "roles": ["admin"],
        "nonce": nonce,
    }
    claims.update(overrides)
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256", headers={"kid": _KID})


def make_jwks_response(public_key, kid=_KID, *, include_alg=True):
    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk.update(kid=kid, use="sig")
    if include_alg:
        jwk["alg"] = "RS256"
    return {"keys": [jwk]}


def sign_token(private_key, payload, kid=_KID):
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})

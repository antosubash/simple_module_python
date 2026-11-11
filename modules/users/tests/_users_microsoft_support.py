"""A Microsoft OIDC client that signs real ID tokens with a local key (no network)."""

from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from users.oauth.microsoft import MicrosoftOidc

KID = "test-kid"
CLIENT_ID = "ms-client"
TENANT = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
OID = "1b2c3d4e-5f60-4a7b-8c9d-0e1f2a3b4c5d"
_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def sign(claims: dict[str, Any], key: Any = _PRIVATE, kid: str = KID) -> str:
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def id_claims(tid: str = TENANT, **overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{tid}/v2.0",
        "aud": CLIENT_ID,
        "sub": "pairwise-sub",
        "iat": now,
        "exp": now + 300,
        "tid": tid,
        "oid": OID,
        "preferred_username": "jane@corp.com",
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


class FakeMicrosoft(MicrosoftOidc):
    """Captures the login's challenge/nonce and answers with a signed ID token.

    ``claims`` overrides the defaults; ``nonce=None`` in it keeps the login's nonce.
    """

    def __init__(self, tenant: str = TENANT, **claims: Any) -> None:
        super().__init__(CLIENT_ID, "secret", tenant)
        self.claims = claims
        self.nonce: str | None = None
        self.challenge: str | None = None
        self.verifier: str | None = None

    async def get_authorization_url(
        self,
        redirect_uri,
        state=None,
        scope=None,
        code_challenge=None,
        code_challenge_method=None,
        extras_params=None,
    ):
        self.challenge = code_challenge
        self.challenge_method = code_challenge_method
        self.nonce = (extras_params or {}).get("nonce")
        return f"https://login.example/authorize?state={state}"

    async def get_access_token(self, code, redirect_uri, code_verifier=None):
        self.verifier = code_verifier
        claims = id_claims(**{"nonce": self.nonce, **self.claims})
        return {"access_token": "at", "id_token": sign(claims)}

    def _cache(self, tid):
        cache = super()._cache(tid)
        cache._keys = {KID: _PRIVATE.public_key()}
        cache._fetched_at = cache._now()
        return cache


def install_microsoft(app, *, trust: bool = True, tenant: str = TENANT, **claims) -> FakeMicrosoft:
    from users.oauth import OAuthProvider

    client = FakeMicrosoft(tenant, **claims)
    app.state.users.oauth_clients["microsoft"] = OAuthProvider(
        "microsoft", "Microsoft", client, trust_email=trust
    )
    return client

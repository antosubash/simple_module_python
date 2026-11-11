"""Microsoft sign-in validates the ID token itself (#876)."""

from __future__ import annotations

import pytest
from _users_microsoft_support import OID, TENANT, FakeMicrosoft, id_claims, sign
from cryptography.hazmat.primitives.asymmetric import rsa
from users.core.oauth_settings import MICROSOFT_CONSUMERS_TENANT
from users.oauth.microsoft import IdTokenError, graph_account_id

_NONCE = "login-nonce"
_OTHER_TENANT = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
_CONSUMERS = str(MICROSOFT_CONSUMERS_TENANT)


async def _identity(client: FakeMicrosoft, token: str, *, trust: bool = False):
    return await client.identity({"id_token": token}, _NONCE, trust_email=trust)


async def test_a_valid_token_gives_the_graph_compatible_identity():
    token = sign(id_claims(nonce=_NONCE))
    assert await _identity(FakeMicrosoft(), token) == (OID, "jane@corp.com", False)


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "another-client"},
        {"iss": "https://login.microsoftonline.com/elsewhere/v2.0"},
        {"nonce": "replayed"},
        {"nonce": None},
        {"exp": 1, "iat": 0},
        {"oid": None},
        {"oid": "not-a-guid"},
        {"tid": None},
        {"azp": "another-client"},
    ],
    ids=["aud", "iss", "nonce", "no-nonce", "expired", "no-oid", "bad-oid", "no-tid", "azp"],
)
async def test_a_bad_token_is_refused(claims):
    token = sign(id_claims(**{"nonce": _NONCE, **claims}))
    with pytest.raises(IdTokenError):
        await _identity(FakeMicrosoft(), token)


async def test_a_token_signed_by_another_key_is_refused():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(IdTokenError):
        await _identity(FakeMicrosoft(), sign(id_claims(nonce=_NONCE), key=other))


@pytest.mark.parametrize("token", [None, "", "not.a.jwt"])
async def test_a_missing_or_garbled_token_is_refused(token):
    with pytest.raises(IdTokenError):
        await FakeMicrosoft().identity({"id_token": token}, _NONCE, trust_email=False)


async def test_a_login_without_a_nonce_is_refused():
    with pytest.raises(IdTokenError):
        await FakeMicrosoft().identity({"id_token": sign(id_claims())}, None, trust_email=False)


async def test_a_pinned_tenant_refuses_another_tenant():
    token = sign(id_claims(_OTHER_TENANT, nonce=_NONCE))
    with pytest.raises(IdTokenError):
        await _identity(FakeMicrosoft(TENANT), token)


@pytest.mark.parametrize(
    "tenant, tid, accepted",
    [
        ("common", _OTHER_TENANT, True),
        ("common", _CONSUMERS, True),
        ("organizations", _OTHER_TENANT, True),
        ("organizations", _CONSUMERS, False),
        ("consumers", _CONSUMERS, True),
        ("consumers", _OTHER_TENANT, False),
    ],
)
async def test_multi_tenant_segments_validate_the_tokens_own_issuer(tenant, tid, accepted):
    token = sign(id_claims(tid, nonce=_NONCE))
    if accepted:
        assert (await _identity(FakeMicrosoft(tenant), token))[0] == OID
    else:
        with pytest.raises(IdTokenError):
            await _identity(FakeMicrosoft(tenant), token)


async def test_the_signed_tid_must_match_the_issuer():
    # Issuer for the other tenant, but ``tid`` claims ours: never accepted.
    claims = {**id_claims(_OTHER_TENANT, nonce=_NONCE), "tid": TENANT}
    with pytest.raises(IdTokenError):
        await _identity(FakeMicrosoft("common"), sign(claims))


@pytest.mark.parametrize(
    "tenant, claims, trusted",
    [
        (TENANT, {}, True),
        (TENANT, {"idp": "https://sts.windows.net/other/"}, False),
        (TENANT, {"idp": f"https://sts.windows.net/{TENANT}/"}, True),
        (TENANT, {"idp": f"https://login.microsoftonline.com/{TENANT}/v2.0"}, True),
        (TENANT, {"preferred_username": "jane_x.com#EXT#@corp.onmicrosoft.com"}, False),
        (TENANT, {"preferred_username": None}, False),
        (TENANT, {"idp": ["https://sts.windows.net/other/"]}, False),
        ("common", {}, False),
    ],
    ids=[
        "member",
        "guest-idp",
        "home-idp-v1",
        "home-idp-v2",
        "guest-ext",
        "no-username",
        "idp-list",
        "common",
    ],
)
async def test_trust_needs_a_member_of_the_pinned_tenant(tenant, claims, trusted):
    token = sign(id_claims(nonce=_NONCE, **claims))
    assert (await _identity(FakeMicrosoft(tenant), token, trust=True))[2] is trusted


@pytest.mark.parametrize(
    "oid, graph_id",
    [
        (OID, OID),
        ("00000000-0000-0000-1a2b-3c4d5e6f7a8b", "1a2b3c4d5e6f7a8b"),
    ],
    ids=["work-or-school", "personal"],
)
def test_account_ids_match_what_graph_returned(oid, graph_id):
    assert graph_account_id(oid) == graph_id


async def test_a_non_email_username_is_no_email():
    token = sign(id_claims(nonce=_NONCE, preferred_username="+43 1 234 5678"))
    assert (await _identity(FakeMicrosoft(), token))[1] is None


async def test_the_upn_claim_wins_over_an_alternate_login_alias():
    claims = id_claims(nonce=_NONCE, preferred_username="alias@corp.com", upn="jane@corp.com")
    assert (await _identity(FakeMicrosoft(), sign(claims)))[1] == "jane@corp.com"

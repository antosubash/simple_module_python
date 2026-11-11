"""Microsoft (Entra) sign-in over OpenID Connect (#876).

The authorization-code flow runs on the tenant's v2.0 endpoints with PKCE and
a nonce, and the identity comes from the validated ID token rather than Graph
``/me``. The endpoints, JWKS URL and issuer are fixed per tenant segment, so
nothing is fetched at boot.
"""

from __future__ import annotations

import re
import secrets
from collections import OrderedDict
from collections.abc import Collection
from typing import Any

import jwt
from auth.oidc_common.jwks import JWKSCache
from httpx_oauth.clients.microsoft import MicrosoftGraphOAuth2
from httpx_oauth.exceptions import HTTPXOAuthError

from users.core.oauth_settings import MICROSOFT_CONSUMERS_TENANT, is_tenant_guid
from users.oauth.identity import OAuthIdentity, email_on_domains, text_or_none

_LOGIN_HOST = "https://login.microsoftonline.com"
_SCOPES = ["openid", "profile", "email"]
_GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# A personal account's ``oid``: its Graph ``id`` (16 hex digits) behind zeros.
_PERSONAL_OID_PREFIX = "00000000-0000-0000-"
# Issuers seen through ``common``/``organizations``; each keeps its own key cache.
_MAX_ISSUER_CACHES = 32
_CONSUMERS_TID = str(MICROSOFT_CONSUMERS_TENANT)


class IdTokenError(HTTPXOAuthError):
    """The token response carried no usable, valid ID token."""


class MicrosoftOidc(MicrosoftGraphOAuth2):
    """Entra v2.0 client that signs in from the ID token, not Graph."""

    uses_pkce = True

    def __init__(self, client_id: str, client_secret: str, tenant: str) -> None:
        super().__init__(client_id, client_secret, tenant=tenant, scopes=_SCOPES, name="microsoft")
        self.tenant = tenant.lower()
        self._jwks_url = f"{_LOGIN_HOST}/{tenant}/discovery/v2.0/keys"
        self._caches: OrderedDict[str, JWKSCache] = OrderedDict()

    async def identity(
        self,
        token: dict[str, Any],
        nonce: str | None,
        *,
        trust_email: bool,
        trusted_domains: Collection[str] = (),
    ) -> OAuthIdentity:
        """Validate the ID token; return the Graph-compatible identity and profile.

        Raises :class:`IdTokenError` for a missing, invalid or foreign token.
        """
        claims, tid = await self._validated_claims(token, nonce)
        oid = claims.get("oid")
        if not isinstance(oid, str) or not _GUID_RE.fullmatch(oid):
            raise IdTokenError("ID token has no object id")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise IdTokenError("ID token has no subject")
        email = _account_email(claims)
        # Proof only for a member of the one tenant the operator pinned: Entra
        # names another ``idp`` for guests and other external identities (#873).
        idp = claims.get("idp")
        member = (
            is_tenant_guid(self.tenant)
            and tid == self.tenant
            and (idp is None or (isinstance(idp, str) and idp in _home_issuers(tid)))
            and not _guest_name(claims)
        )
        trusted = trust_email and member and email is not None and "#EXT#" not in email.upper()
        # A member's address on a domain the operator owns is proof too (#878).
        on_domain = _domain_email(claims, trusted_domains) if member else None
        if on_domain is not None:
            email, trusted = on_domain, True
        return OAuthIdentity(
            account_id=graph_account_id(oid),
            email=email,
            email_verified=bool(trusted),
            subject=text_or_none(claims.get("sub")),
            username=email or text_or_none(claims.get("preferred_username")),
            display_name=text_or_none(claims.get("name")),
            extra={"oid": oid, "tid": tid},
        )

    async def _validated_claims(
        self, token: dict[str, Any], nonce: str | None
    ) -> tuple[dict[str, Any], str]:
        id_token = token.get("id_token")
        if not isinstance(id_token, str) or not nonce:
            raise IdTokenError("ID token missing")
        tid = _unverified_tid(id_token)
        if tid is None or not self._accepts_tenant(tid):
            raise IdTokenError("ID token from an unexpected tenant")
        claims = await self._cache(tid).validate_jwt(id_token)
        if claims is None or claims.get("tid") != tid:
            raise IdTokenError("ID token validation failed")
        claimed_nonce = claims.get("nonce")
        if not isinstance(claimed_nonce, str) or not secrets.compare_digest(
            claimed_nonce.encode(), nonce.encode()
        ):
            raise IdTokenError("ID token nonce mismatch")
        return claims, tid

    def _accepts_tenant(self, tid: str) -> bool:
        if self.tenant == "consumers":
            return tid == _CONSUMERS_TID
        if self.tenant == "organizations":
            return tid != _CONSUMERS_TID
        if _GUID_RE.fullmatch(self.tenant):
            return tid == self.tenant
        # ``common`` or a verified-domain tenant: the authorize endpoint pins it.
        return True

    def _cache(self, tid: str) -> JWKSCache:
        cache = self._caches.get(tid)
        if cache is None:
            cache = JWKSCache(
                self._jwks_url, issuer=f"{_LOGIN_HOST}/{tid}/v2.0", audience=self.client_id
            )
            self._caches[tid] = cache
            if len(self._caches) > _MAX_ISSUER_CACHES:
                self._caches.popitem(last=False)
        else:
            self._caches.move_to_end(tid)
        return cache


def graph_account_id(oid: str) -> str:
    """The Graph ``id`` for an ``oid``, so links made through Graph keep matching.

    Work and school accounts: Graph ``id`` is the ``oid``. Personal accounts:
    Graph returns 16 hex digits, which ``oid`` carries after a zero prefix.
    """
    if oid.startswith(_PERSONAL_OID_PREFIX):
        return oid[len(_PERSONAL_OID_PREFIX) :].replace("-", "")
    return oid


def _account_email(claims: dict[str, Any]) -> str | None:
    """The sign-in address: the optional ``upn`` claim, else ``preferred_username``.

    With email as an alternate login ID, ``preferred_username`` is whatever the
    user typed; an app registration that adds the ``upn`` optional claim gets the
    UPN Graph used to return. A phone-number username is no email.
    """
    for name in ("upn", "preferred_username"):
        value = claims.get(name)
        if isinstance(value, str) and "@" in value:
            return value
    return None


def _guest_name(claims: dict[str, Any]) -> bool:
    """A guest's UPN (``#EXT#``) in any name claim: never a member, whatever else it says."""
    return any(
        isinstance(claims.get(name), str) and "#EXT#" in claims[name].upper()
        for name in ("upn", "preferred_username")
    )


def _domain_email(claims: dict[str, Any], domains: Collection[str]) -> str | None:
    """The UPN or username on a trusted domain, else a domain-verified ``email``.

    ``email`` is editable by the user and unverified unless Entra marks its
    domain as verified with the ``xms_edov`` optional claim.
    """
    names = ["upn", "preferred_username"]
    if claims.get("xms_edov") is True:
        names.append("email")
    for name in names:
        value = claims.get(name)
        if (
            isinstance(value, str)
            and "#EXT#" not in value.upper()
            and email_on_domains(value, domains)
        ):
            return value
    return None


def _home_issuers(tid: str) -> set[str]:
    """``idp`` values that mean the tenant itself authenticated the account (v1 and v2)."""
    return {f"{_LOGIN_HOST}/{tid}/v2.0", f"https://sts.windows.net/{tid}/"}


def _unverified_tid(id_token: str) -> str | None:
    """The token's ``tid``, read only to choose the issuer it must then verify against."""
    try:
        tid = jwt.decode(id_token, options={"verify_signature": False}).get("tid")
    except jwt.PyJWTError:
        return None
    return tid if isinstance(tid, str) and _GUID_RE.fullmatch(tid) else None

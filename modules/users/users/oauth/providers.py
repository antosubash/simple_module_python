"""OAuth/OIDC provider client factory.

Constructs the ``httpx_oauth`` clients for every provider that has both
``client_id`` and ``client_secret`` set in :class:`UsersSettings`. A provider
with no credentials is silently skipped — that's the "feature flag" knob.

Lives in its own module so :func:`UsersModule.register_routes` can import it
without dragging the heavy ``httpx_oauth`` packages into the cold-start path
when no provider is configured.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple, TypedDict

from auth.oidc_common.session import pkce_challenge

from users.core.oauth_settings import is_tenant_guid
from users.oauth.identity import OAuthIdentity, text_or_none

if TYPE_CHECKING:
    from httpx_oauth.oauth2 import BaseOAuth2

    from users.core.settings import UsersSettings

logger = logging.getLogger(__name__)


class LoginSecrets(TypedDict):
    """Per-login PKCE verifier and OIDC nonce, kept in the session with the state."""

    verifier: str
    nonce: str


class OAuthProvider(NamedTuple):
    """One configured provider — name is the URL segment (``/auth/<name>``)."""

    name: str
    display_name: str
    client: BaseOAuth2
    # Microsoft only: the operator trusts member UPNs of the pinned tenant (#873).
    trust_email: bool = False
    # Addresses on these domains count as proof for this provider (#878).
    trusted_domains: frozenset[str] = frozenset()

    @property
    def uses_pkce(self) -> bool:
        """Whether a login carries a PKCE verifier and an OIDC nonce (#876)."""
        return getattr(self.client, "uses_pkce", False) is True

    async def authorization_url(self, callback: str, state: str, login: LoginSecrets | None) -> str:
        """The IdP URL to send the browser to, bound to this login's secrets."""
        if login is None:
            return await self.client.get_authorization_url(callback, state)
        return await self.client.get_authorization_url(
            callback,
            state,
            code_challenge=pkce_challenge(login["verifier"]),
            code_challenge_method="S256",
            extras_params={"nonce": login["nonce"]},
        )

    async def exchange_code(
        self, code: str, callback: str, login: LoginSecrets | None
    ) -> dict[str, Any]:
        """The token endpoint's response for this authorization code."""
        if login is None:
            return await self.client.get_access_token(code, callback)
        return await self.client.get_access_token(code, callback, code_verifier=login["verifier"])

    async def get_identity(
        self, token: dict[str, Any], login: LoginSecrets | None = None
    ) -> OAuthIdentity:
        """Who signed in, the email and whether the provider proved it, and the profile.

        ``token`` is the whole token response, so an OIDC provider can read its
        ID token (#876). Each provider reads email proof from its own profile
        shape; only a positive proof links an existing account or marks a new
        one verified (#622). An address on one of the provider's trusted
        domains counts as proof too (#878).
        """
        if self.uses_pkce:
            return await self.client.identity(
                token,
                login["nonce"] if login else None,
                trust_email=self.trust_email,
                trusted_domains=self.trusted_domains,
            )
        identity = await self._profile_identity(token["access_token"])
        return identity.trusting(self.trusted_domains)

    async def _profile_identity(self, access_token: str) -> OAuthIdentity:
        if self.name == "oidc":
            profile = await self.client.get_profile(access_token)
            return OAuthIdentity(
                str(profile["sub"]),
                profile.get("email"),
                profile.get("email_verified") is True,
                subject=str(profile["sub"]),
                username=text_or_none(profile.get("preferred_username")),
                display_name=text_or_none(profile.get("name")),
                domain_trust_allowed=profile.get("email_verified") is not False,
            )
        if self.name == "google":
            return _google_identity(await self.client.get_profile(access_token))
        if self.name != "github":
            account_id, email = await self.client.get_id_email(access_token)
            return OAuthIdentity(account_id, email, False)
        # One /user request: ``get_id_email`` would fetch it again internally.
        profile = await self.client.get_profile(access_token)
        account_id, email = str(profile["id"]), profile.get("email")
        if email is None:  # no public email: get_id_email falls back to /user/emails
            account_id, email = await self.client.get_id_email(access_token)
        verified = email is not None and await _github_verified(self.client, access_token, email)
        return OAuthIdentity(
            account_id,
            email,
            verified,
            subject=account_id,
            username=text_or_none(profile.get("login")),
            display_name=text_or_none(profile.get("name")),
        )


def _google_identity(profile: dict[str, Any]) -> OAuthIdentity:
    """People API profile → resourceName, primary email and its ``metadata.verified``."""
    subject = str(profile["resourceName"])
    names = [n for n in profile.get("names") or [] if isinstance(n, dict)]
    name = next((n for n in names if n.get("metadata", {}).get("primary")), None)
    display_name = text_or_none((name or (names[0] if names else {})).get("displayName"))
    primary = next(
        (e for e in profile.get("emailAddresses", []) if e.get("metadata", {}).get("primary")),
        None,
    )
    if primary is None:
        return OAuthIdentity(subject, None, False, subject=subject, display_name=display_name)
    return OAuthIdentity(
        subject,
        primary.get("value"),
        primary.get("metadata", {}).get("verified") is True,
        subject=subject,
        username=primary.get("value"),
        display_name=display_name,
        domain_trust_allowed=primary.get("metadata", {}).get("verified") is not False,
    )


async def _github_verified(client: Any, token: str, email: str) -> bool:
    try:
        emails = await client.get_emails(token)
    except Exception:
        return False
    return any(e.get("email") == email and e.get("verified") is True for e in emails)


def build_clients(settings: UsersSettings) -> list[OAuthProvider]:
    """Return one entry per provider that has both id and secret configured.

    The generic OIDC provider also requires a discovery URL. If discovery
    fetch fails at construction time, the provider is logged and skipped
    rather than raising — a misconfigured IdP must not break boot.
    """
    out: list[OAuthProvider] = []

    if settings.oauth_google_client_id and settings.oauth_google_client_secret:
        from users.oauth.google import GoogleWithNames

        out.append(
            OAuthProvider(
                "google",
                "Google",
                GoogleWithNames(
                    settings.oauth_google_client_id,
                    settings.oauth_google_client_secret,
                ),
            )
        )

    if settings.oauth_github_client_id and settings.oauth_github_client_secret:
        from httpx_oauth.clients.github import GitHubOAuth2

        out.append(
            OAuthProvider(
                "github",
                "GitHub",
                GitHubOAuth2(
                    settings.oauth_github_client_id,
                    settings.oauth_github_client_secret,
                ),
            )
        )

    if settings.oauth_microsoft_client_id and settings.oauth_microsoft_client_secret:
        from users.oauth.microsoft import MicrosoftOidc

        out.append(
            OAuthProvider(
                "microsoft",
                "Microsoft",
                MicrosoftOidc(
                    settings.oauth_microsoft_client_id,
                    settings.oauth_microsoft_client_secret,
                    settings.oauth_microsoft_tenant or "common",
                ),
                trust_email=settings.oauth_microsoft_trust_tenant_upn
                and is_tenant_guid(settings.oauth_microsoft_tenant),
            )
        )

    if (
        settings.oauth_oidc_client_id
        and settings.oauth_oidc_client_secret
        and settings.oauth_oidc_discovery_url
    ):
        from httpx_oauth.clients.openid import OpenID, OpenIDConfigurationError

        try:
            client = OpenID(
                settings.oauth_oidc_client_id,
                settings.oauth_oidc_client_secret,
                settings.oauth_oidc_discovery_url,
                name="oidc",
            )
        except OpenIDConfigurationError:
            logger.exception(
                "OIDC discovery failed for %s — provider disabled",
                settings.oauth_oidc_discovery_url,
            )
        else:
            out.append(
                OAuthProvider(
                    "oidc",
                    settings.oauth_oidc_display_name or "OIDC",
                    client,
                )
            )

    return [p._replace(trusted_domains=settings.trusted_domains(p.name)) for p in out]


def build_client_map(settings: UsersSettings) -> dict[str, OAuthProvider]:
    """Configured providers keyed by name for O(1) request-time lookup."""
    return {p.name: p for p in build_clients(settings)}


def provider_buttons(clients: dict[str, OAuthProvider]) -> list[dict[str, str]]:
    """Login-button descriptors derived from a built client map."""
    return [{"name": p.name, "display_name": p.display_name} for p in clients.values()]
